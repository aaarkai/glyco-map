"""
Event Quality Evaluation

Evaluates meal/intervention events against CGM data to assess
whether they support reliable causal analysis.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


class EventQualityEvaluator:
    """
    Evaluates event quality for causal analysis by checking:
    1. Overlap with CGM coverage
    2. Isolation from other events
    3. Sufficient pre-event baseline
    """

    def __init__(self):
        # Configuration for quality thresholds
        self.min_baseline_minutes = 60  # Need 60 min clean baseline before event
        self.min_isolation_minutes = 30  # Need 30 min between events
        self.min_during_coverage = 0.8  # Need 80% coverage during event
        self.min_baseline_coverage = 0.9  # Need 90% coverage in baseline period

    def _parse_timestamp(self, value: str) -> datetime:
        """
        Parse RFC 3339 timestamps, including Z suffix.
        """
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            if value.endswith("Z") or value.endswith("z"):
                return datetime.fromisoformat(value[:-1] + "+00:00")
            raise

    def load_cgm_data(self, filepath: str) -> Dict[str, Any]:
        """
        Load CGM time series data from JSON file.

        Args:
            filepath: Path to CGM JSON file

        Returns:
            CGM data dictionary
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            raise ValueError(f"Failed to load CGM data: {e}")

    def load_events(self, filepath: str) -> Dict[str, Any]:
        """
        Load events data from JSON file.

        Args:
            filepath: Path to events JSON file

        Returns:
            Events data dictionary
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            raise ValueError(f"Failed to load events data: {e}")

    def parse_cgm_timestamps(self, cgm_data: Dict[str, Any]) -> List[datetime]:
        """
        Parse CGM timestamps into datetime objects.

        Args:
            cgm_data: CGM data dictionary

        Returns:
            List of datetime objects
        """
        timestamps = []
        for sample in cgm_data.get('samples', []):
            try:
                ts = self._parse_timestamp(sample['timestamp'])
                timestamps.append(ts)
            except ValueError:
                # Skip invalid timestamps
                continue
        return sorted(timestamps)

    def parse_event_times(self, event: Dict[str, Any]) -> Tuple[datetime, Optional[datetime]]:
        """
        Parse event start and end times.

        Args:
            event: Event dictionary

        Returns:
            Tuple of (start_time, end_time_or_none)
        """
        try:
            start_time = self._parse_timestamp(event['start_time'])
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid event start_time: {e}")

        end_time = None
        if 'end_time' in event:
            try:
                end_time = self._parse_timestamp(event['end_time'])
            except ValueError as e:
                raise ValueError(f"Invalid event end_time: {e}")

        return start_time, end_time

    def check_cgm_overlap(
        self,
        event: Dict[str, Any],
        cgm_timestamps: List[datetime],
        cgm_interval: float
    ) -> Dict[str, Any]:
        """
        Check event overlap with CGM data coverage.

        Args:
            event: Event dictionary
            cgm_timestamps: List of CGM timestamps
            cgm_interval: CGM sampling interval in minutes

        Returns:
            Overlap analysis dictionary
        """
        if not cgm_timestamps:
            return {
                'has_overlap': False,
                'coverage_fraction': 0.0,
                'gap_minutes': 0.0,
                'issues': ['No CGM data available'],
                'recommendation': 'Cannot analyze event without CGM data'
            }

        start_time, end_time = self.parse_event_times(event)

        # If no end time, assume event duration is 30 minutes
        if end_time is None:
            end_time = start_time + timedelta(minutes=30)

        event_duration = (end_time - start_time).total_seconds() / 60

        # Find CGM samples within event window
        samples_during = [
            ts for ts in cgm_timestamps
            if start_time <= ts <= end_time
        ]

        # Calculate expected number of samples
        # Add 1 because we expect samples at both start and end times
        expected_samples = (event_duration / cgm_interval) + 1
        actual_samples = len(samples_during)
        coverage_fraction = actual_samples / expected_samples if expected_samples > 0 else 0

        # Cap coverage fraction at 1.0 (100%)
        coverage_fraction = min(coverage_fraction, 1.0)

        # Find gaps
        gaps = []
        for i in range(1, len(samples_during)):
            gap = (samples_during[i] - samples_during[i-1]).total_seconds() / 60
            if gap > cgm_interval * 1.5:  # Gap > 1.5x expected interval
                gaps.append({
                    'start': samples_during[i-1].isoformat(),
                    'end': samples_during[i].isoformat(),
                    'duration_minutes': round(gap, 2)
                })

        total_gap_minutes = sum(gap['duration_minutes'] for gap in gaps)

        issues = []
        if coverage_fraction < self.min_during_coverage:
            issues.append(f'Low CGM coverage during event: {coverage_fraction:.1%}')

        if total_gap_minutes > event_duration * 0.2:  # >20% gaps
            issues.append(f'Large gaps during event: {total_gap_minutes} minutes')

        return {
            'has_overlap': actual_samples > 0,
            'coverage_fraction': round(coverage_fraction, 3),
            'expected_samples': round(expected_samples, 1),
            'actual_samples': actual_samples,
            'gap_count': len(gaps),
            'total_gap_minutes': round(total_gap_minutes, 2),
            'gaps': gaps,
            'issues': issues,
            'recommendation': self._get_overlap_recommendation(coverage_fraction, issues)
        }

    def check_event_isolation(
        self,
        event: Dict[str, Any],
        all_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Check if event is isolated from other events.

        Args:
            event: Event to check
            all_events: List of all events (including the one being checked)

        Returns:
            Isolation analysis dictionary
        """
        event_start, event_end = self.parse_event_times(event)

        if event_end is None:
            event_end = event_start + timedelta(minutes=30)

        # Find nearest events
        min_before_gap = float('inf')
        min_after_gap = float('inf')
        overlapping_events = []

        for other_event in all_events:
            if other_event['event_id'] == event['event_id']:
                continue

            other_start, other_end = self.parse_event_times(other_event)
            if other_end is None:
                other_end = other_start + timedelta(minutes=30)

            # Check for overlap
            if not (event_end < other_start or event_start > other_end):
                overlapping_events.append({
                    'event_id': other_event['event_id'],
                    'label': other_event.get('label', 'Unlabeled event'),
                    'overlap_start': max(event_start, other_start).isoformat(),
                    'overlap_end': min(event_end, other_end).isoformat()
                })

            # Check gap before event
            if other_end <= event_start:
                gap_before = (event_start - other_end).total_seconds() / 60
                min_before_gap = min(min_before_gap, gap_before)

            # Check gap after event
            if other_start >= event_end:
                gap_after = (other_start - event_end).total_seconds() / 60
                min_after_gap = min(min_after_gap, gap_after)

        # Determine nearest neighbor gap
        nearest_gap = min(min_before_gap, min_after_gap)
        if nearest_gap == float('inf'):
            nearest_gap = None

        issues = []
        if overlapping_events:
            issues.append(f'Overlaps with {len(overlapping_events)} other event(s)')

        if nearest_gap is not None and nearest_gap < self.min_isolation_minutes:
            issues.append(f'Close to other events: {nearest_gap} minutes')

        return {
            'is_isolated': len(overlapping_events) == 0,
            'overlapping_events': overlapping_events,
            'nearest_event_gap_minutes': round(nearest_gap, 2) if nearest_gap else None,
            'min_before_gap': round(min_before_gap, 2) if min_before_gap != float('inf') else None,
            'min_after_gap': round(min_after_gap, 2) if min_after_gap != float('inf') else None,
            'issues': issues,
            'recommendation': self._get_isolation_recommendation(overlapping_events, nearest_gap)
        }

    def check_pre_event_baseline(
        self,
        event: Dict[str, Any],
        cgm_timestamps: List[datetime],
        cgm_interval: float
    ) -> Dict[str, Any]:
        """
        Check for sufficient pre-event baseline data.

        Args:
            event: Event dictionary
            cgm_timestamps: List of CGM timestamps
            cgm_interval: CGM sampling interval in minutes

        Returns:
            Baseline analysis dictionary
        """
        if not cgm_timestamps:
            return {
                'has_sufficient_baseline': False,
                'baseline_minutes': 0,
                'coverage_fraction': 0.0,
                'issues': ['No CGM data available'],
                'recommendation': 'Cannot establish baseline without CGM data'
            }

        event_start, _ = self.parse_event_times(event)

        # Define baseline window
        baseline_start = event_start - timedelta(minutes=self.min_baseline_minutes)

        # Find CGM samples in baseline window
        baseline_samples = [
            ts for ts in cgm_timestamps
            if baseline_start <= ts < event_start
        ]

        expected_samples = self.min_baseline_minutes / cgm_interval
        actual_samples = len(baseline_samples)
        coverage_fraction = actual_samples / expected_samples if expected_samples > 0 else 0

        # Check for gaps in baseline
        gaps = []
        max_gap = 0
        for i in range(1, len(baseline_samples)):
            gap = (baseline_samples[i] - baseline_samples[i-1]).total_seconds() / 60
            max_gap = max(max_gap, gap)
            if gap > cgm_interval * 2:  # Gap > 2x expected interval
                gaps.append({
                    'start': baseline_samples[i-1].isoformat(),
                    'end': baseline_samples[i].isoformat(),
                    'duration_minutes': round(gap, 2)
                })

        issues = []
        if coverage_fraction < self.min_baseline_coverage:
            issues.append(f'Insufficient baseline coverage: {coverage_fraction:.1%}' + \
                         f' (need {self.min_baseline_coverage:.0%})')

        if max_gap > cgm_interval * 5:  # Gap > 5x interval is concerning (more lenient)
            issues.append(f'Large gap in baseline: {max_gap:.1f} minutes')

        # Calculate baseline variability if enough samples
        baseline_variability = None
        if actual_samples >= 3:
            # For now, just note we could calculate this
            baseline_variability = 'calculable'

        return {
            'has_sufficient_baseline': coverage_fraction >= self.min_baseline_coverage and not issues,
            'baseline_minutes': self.min_baseline_minutes,
            'actual_baseline_minutes': (event_start - baseline_start).total_seconds() / 60,
            'coverage_fraction': round(coverage_fraction, 3),
            'expected_samples': round(expected_samples, 1),
            'actual_samples': actual_samples,
            'gap_count': len(gaps),
            'max_gap_minutes': round(max_gap, 2),
            'gaps': gaps,
            'issues': issues,
            'recommendation': self._get_baseline_recommendation(coverage_fraction, issues)
        }

    def evaluate_event_quality(
        self,
        event: Dict[str, Any],
        all_events: List[Dict[str, Any]],
        cgm_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform complete quality evaluation for a single event.

        Args:
            event: Event to evaluate
            all_events: List of all events
            cgm_data: CGM data dictionary (optional)

        Returns:
            Complete quality evaluation dictionary
        """
        if cgm_data:
            cgm_timestamps = self.parse_cgm_timestamps(cgm_data)
            cgm_interval = cgm_data.get('sampling_interval_minutes', 5.0)
        else:
            cgm_timestamps = []
            cgm_interval = 5.0

        overlap = self.check_cgm_overlap(event, cgm_timestamps, cgm_interval)
        isolation = self.check_event_isolation(event, all_events)
        baseline = self.check_pre_event_baseline(event, cgm_timestamps, cgm_interval)

        # Overall quality assessment
        quality_issues = []
        if not cgm_data:
            quality_issues.append('No CGM data available')
        elif not overlap.get('has_overlap', False):
            quality_issues.append('No CGM overlap')
        else:
            quality_issues.extend(overlap.get('issues', []))

        if not isolation.get('is_isolated', True):
            quality_issues.extend(isolation.get('issues', []))

        if cgm_data and not baseline.get('has_sufficient_baseline', False):
            quality_issues.extend(baseline.get('issues', []))

        # Quality score (0-1)
        quality_score = 1.0
        if quality_issues:
            # Check for critical issues that make event unusable
            critical_issues = ['No CGM data available', 'No CGM overlap']
            if any(issue in quality_issues for issue in critical_issues):
                quality_score = 0.0
            else:
                # Each major issue reduces quality by 0.2
                quality_score = max(0.0, 1.0 - (len(quality_issues) * 0.2))

        return {
            'event_id': event['event_id'],
            'label': event.get('label', 'Unlabeled event'),
            'quality_score': round(quality_score, 2),
            'is_usable_for_analysis': quality_score >= 0.6,
            'quality_issues': quality_issues,
            'recommendations': [
                overlap.get('recommendation', ''),
                isolation.get('recommendation', ''),
                baseline.get('recommendation', '')
            ],
            'detailed_analysis': {
                'cgm_overlap': overlap,
                'event_isolation': isolation,
                'pre_event_baseline': baseline
            }
        }

    def evaluate_all_events(
        self,
        events_data: Dict[str, Any],
        cgm_filepath: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate quality for all events in a collection.

        Args:
            events_data: Events collection dictionary
            cgm_filepath: Path to CGM data file (optional)

        Returns:
            Quality evaluation for all events
        """
        if cgm_filepath:
            cgm_data = self.load_cgm_data(cgm_filepath)
        else:
            cgm_data = None

        events = events_data.get('events', [])
        if not events:
            return {
                'evaluator_version': '1.0.0',
                'total_events': 0,
                'usable_events': 0,
                'evaluations': [],
                'summary': 'No events to evaluate'
            }

        evaluations = []
        usable_count = 0

        for event in events:
            evaluation = self.evaluate_event_quality(event, events, cgm_data)
            evaluations.append(evaluation)
            if evaluation['is_usable_for_analysis']:
                usable_count += 1

        return {
            'evaluator_version': '1.0.0',
            'events_id': events_data.get('events_id', 'unknown'),
            'subject_id': events_data.get('subject_id', 'unknown'),
            'total_events': len(events),
            'usable_events': usable_count,
            'usability_fraction': round(usable_count / len(events), 2) if events else 0.0,
            'evaluations': evaluations,
            'summary': f'{usable_count}/{len(events)} events are suitable for causal analysis'
        }

    def print_evaluation_summary(self, evaluation: Dict[str, Any]) -> None:
        """
        Print human-readable evaluation summary.

        Args:
            evaluation: Event quality evaluation dictionary
        """
        import sys

        print(f"\n{'='*70}", file=sys.stderr)
        print(f"EVENT QUALITY EVALUATION", file=sys.stderr)
        print(f"{'='*70}\n", file=sys.stderr)

        print(f"Event: {evaluation['label']}", file=sys.stderr)
        print(f"Event ID: {evaluation['event_id']}", file=sys.stderr)
        print(f"Quality Score: {evaluation['quality_score']}/1.0", file=sys.stderr)
        print(f"Usable for Analysis: {'✓' if evaluation['is_usable_for_analysis'] else '✗'}", file=sys.stderr)

        if evaluation['quality_issues']:
            print(f"\nQuality Issues:", file=sys.stderr)
            for issue in evaluation['quality_issues']:
                print(f"  • {issue}", file=sys.stderr)

        print(f"\nDetailed Analysis:", file=sys.stderr)
        print(f"{'-'*70}", file=sys.stderr)

        # CGM Overlap
        overlap = evaluation['detailed_analysis']['cgm_overlap']
        print(f"\n1. CGM Overlap:", file=sys.stderr)
        print(f"   Coverage: {overlap['coverage_fraction']:.1%} " +
              f"({overlap['actual_samples']}/{overlap['expected_samples']:.0f} samples)", file=sys.stderr)
        if overlap['gap_count'] > 0:
            print(f"   Gaps: {overlap['gap_count']} (total {overlap['total_gap_minutes']} min)",
                  file=sys.stderr)
        if overlap['issues']:
            for issue in overlap['issues']:
                print(f"   ⚠ {issue}", file=sys.stderr)

        # Event Isolation
        isolation = evaluation['detailed_analysis']['event_isolation']
        print(f"\n2. Event Isolation:", file=sys.stderr)
        if isolation['overlapping_events']:
            print(f"   Overlaps with {len(isolation['overlapping_events'])} event(s)",
                  file=sys.stderr)
            for overlap_event in isolation['overlapping_events']:
                print(f"     - {overlap_event['label']}", file=sys.stderr)
        if isolation['nearest_event_gap_minutes']:
            print(f"   Nearest event: {isolation['nearest_event_gap_minutes']} minutes away",
                  file=sys.stderr)
        if isolation['issues']:
            for issue in isolation['issues']:
                print(f"   ⚠ {issue}", file=sys.stderr)

        # Pre-event Baseline
        baseline = evaluation['detailed_analysis']['pre_event_baseline']
        print(f"\n3. Pre-event Baseline:", file=sys.stderr)
        print(f"   Coverage: {baseline['coverage_fraction']:.1%} " +
              f"({baseline['actual_samples']}/{baseline['expected_samples']:.0f} samples)",
              file=sys.stderr)
        print(f"   Baseline window: {baseline['baseline_minutes']} minutes", file=sys.stderr)
        if baseline['gap_count'] > 0:
            print(f"   Gaps: {baseline['gap_count']} (max {baseline['max_gap_minutes']} min)",
                  file=sys.stderr)
        if baseline['issues']:
            for issue in baseline['issues']:
                print(f"   ⚠ {issue}", file=sys.stderr)

        print(f"\nRecommendations:", file=sys.stderr)
        print(f"{'-'*70}", file=sys.stderr)
        for rec in evaluation['recommendations']:
            if rec:
                print(f"• {rec}", file=sys.stderr)

        print(f"\n{'='*70}\n", file=sys.stderr)

    def _get_overlap_recommendation(self, coverage_fraction: float, issues: List[str]) -> str:
        """Generate recommendation based on overlap analysis."""
        if coverage_fraction < 0.5:
            return 'Insufficient CGM coverage. Consider event outside CGM recording period.'
        elif coverage_fraction < 0.8:
            return 'Low CGM coverage during event. Results may be unreliable.'
        elif issues:
            return f'Address CGM coverage issues: {", ".join(issues)}'
        else:
            return 'CGM coverage during event is sufficient for analysis.'

    def _get_isolation_recommendation(
        self,
        overlapping_events: List[Dict],
        nearest_gap: Optional[float]
    ) -> str:
        """Generate recommendation based on isolation analysis."""
        if overlapping_events:
            return 'Event overlaps with other events. Consider excluding from analysis.'
        elif nearest_gap is not None and nearest_gap < 30:
            return f'Event is close to other events ({nearest_gap:.0f} min). ' + \
                   'Check for confounding effects.'
        else:
            return 'Event is well-isolated for analysis.'

    def _get_baseline_recommendation(self, coverage_fraction: float, issues: List[str]) -> str:
        """Generate recommendation based on baseline analysis."""
        if coverage_fraction < 0.5:
            return 'Insufficient baseline data. Cannot establish pre-event glucose pattern.'
        elif coverage_fraction < 0.9:
            return 'Limited baseline coverage. Exercise caution in interpreting results.'
        elif issues:
            return f'Improve baseline data quality: {", ".join(issues)}'
        else:
            return 'Pre-event baseline is sufficient for analysis.'
