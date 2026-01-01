"""
CGM Signal Sanity Report Generator

Analyzes imported CGM time series for data quality issues.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict


class CGMSanityReport:
    """
    Generates signal sanity reports for CGM time series.
    """

    def __init__(self):
        pass

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

    def load_schema(self, filepath: str) -> Dict[str, Any]:
        """
        Load CGM time series schema from JSON file.

        Args:
            filepath: Path to the schema JSON file

        Returns:
            Dictionary containing the schema data

        Raises:
            ValueError: If the file cannot be loaded or parsed
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            raise ValueError(f"Failed to load schema file: {e}")

    def calculate_coverage(self, samples: List[Dict[str, Any]], expected_interval_minutes: float) -> Dict[str, Any]:
        """
        Calculate data coverage statistics.

        Args:
            samples: List of samples from the schema
            expected_interval_minutes: Expected sampling interval in minutes

        Returns:
            Dictionary with coverage metrics
        """
        if not samples:
            return {
                "total_expected_minutes": 0,
                "total_actual_minutes": 0,
                "coverage_percentage": 0.0,
                "missing_intervals": 0,
                "total_intervals": 0
            }

        # Parse timestamps
        timestamps = [self._parse_timestamp(s["timestamp"]) for s in samples]

        # Calculate expected vs actual intervals
        time_span_minutes = (timestamps[-1] - timestamps[0]).total_seconds() / 60
        expected_intervals_float = (
            time_span_minutes / expected_interval_minutes
            if expected_interval_minutes > 0
            else 0
        )
        actual_intervals = len(samples) - 1
        expected_intervals = int(round(expected_intervals_float)) if expected_intervals_float > 0 else 0
        if expected_intervals < actual_intervals:
            expected_intervals = actual_intervals

        # Count gaps larger than 1.5x expected interval
        gaps = 0
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
            if gap > expected_interval_minutes * 1.5:
                gaps += 1

        return {
            "total_expected_minutes": time_span_minutes,
            "total_actual_minutes": actual_intervals * expected_interval_minutes,
            "coverage_percentage": (actual_intervals / expected_intervals) * 100 if expected_intervals > 0 else 0,
            "missing_intervals": max(expected_intervals - actual_intervals, 0),
            "total_intervals": expected_intervals,
            "large_gaps": gaps
        }

    def check_sampling_regularity(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check the regularity of sampling intervals.

        Args:
            samples: List of samples from the schema

        Returns:
            Dictionary with regularity metrics
        """
        if len(samples) < 2:
            return {
                "mean_interval_minutes": 0,
                "std_interval_minutes": 0,
                "cv_interval": 0,
                "irregular_intervals": 0,
                "irregular_percentage": 0,
                "is_regular": True
            }

        # Parse timestamps and calculate intervals
        timestamps = [self._parse_timestamp(s["timestamp"]) for s in samples]
        intervals = []

        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
            intervals.append(interval)

        import numpy as np

        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        cv_interval = std_interval / mean_interval if mean_interval > 0 else 0

        # Count irregular intervals (>20% deviation from mean)
        irregular_threshold = mean_interval * 0.2
        irregular_count = sum(1 for interval in intervals
                            if abs(interval - mean_interval) > irregular_threshold)

        return {
            "mean_interval_minutes": float(mean_interval),
            "std_interval_minutes": float(std_interval),
            "cv_interval": float(cv_interval),
            "irregular_intervals": int(irregular_count),
            "irregular_percentage": float((irregular_count / len(intervals)) * 100 if intervals else 0),
            "is_regular": bool(cv_interval < 0.1)  # CV < 10% is considered regular
        }

    def analyze_extreme_values(self, samples: List[Dict[str, Any]], unit: str) -> Dict[str, Any]:
        """
        Analyze extreme glucose values.

        Args:
            samples: List of samples from the schema
            unit: Glucose unit ('mg/dL' or 'mmol/L')

        Returns:
            Dictionary with extreme value statistics
        """
        values = [s["glucose_value"] for s in samples]

        if not values:
            return {
                "min_value": None,
                "max_value": None,
                "mean_value": None,
                "median_value": None,
                "extreme_low": 0,
                "extreme_high": 0,
                "unit": unit
            }

        import numpy as np

        # Define extreme thresholds based on unit
        if unit == "mmol/L":
            low_threshold = 3.0  # < 54 mg/dL
            high_threshold = 15.0  # > 270 mg/dL
        else:  # mg/dL
            low_threshold = 54
            high_threshold = 270

        extreme_low = sum(1 for v in values if v < low_threshold)
        extreme_high = sum(1 for v in values if v > high_threshold)

        return {
            "min_value": float(np.min(values)),
            "max_value": float(np.max(values)),
            "mean_value": float(np.mean(values)),
            "median_value": float(np.median(values)),
            "extreme_low": extreme_low,
            "extreme_high": extreme_high,
            "extreme_low_percentage": (extreme_low / len(values)) * 100,
            "extreme_high_percentage": (extreme_high / len(values)) * 100,
            "unit": unit
        }

    def detect_suspicious_changes(self, samples: List[Dict[str, Any]], unit: str) -> Dict[str, Any]:
        """
        Detect suspicious rapid drops or spikes.

        Args:
            samples: List of samples from the schema
            unit: Glucose unit ('mg/dL' or 'mmol/L')

        Returns:
            Dictionary with suspicious change statistics
        """
        if len(samples) < 3:
            return {
                "suspicious_drops": [],
                "suspicious_spikes": [],
                "total_suspicious": 0
            }

        # Define thresholds based on unit
        if unit == "mmol/L":
            drop_threshold = 2.0  # > 2 mmol/L drop
            spike_threshold = 2.0  # > 2 mmol/L spike
        else:  # mg/dL
            drop_threshold = 36  # > 36 mg/dL drop
            spike_threshold = 36  # > 36 mg/dL spike

        suspicious_drops = []
        suspicious_spikes = []

        for i in range(1, len(samples) - 1):
            prev_val = samples[i-1]["glucose_value"]
            curr_val = samples[i]["glucose_value"]
            next_val = samples[i+1]["glucose_value"]

            # Calculate changes
            change_to_curr = curr_val - prev_val
            change_from_curr = next_val - curr_val

            # Check for suspicious drop (sharp drop followed by recovery)
            if change_to_curr < -drop_threshold and change_from_curr > drop_threshold * 0.5:
                suspicious_drops.append({
                    "index": i,
                    "timestamp": samples[i]["timestamp"],
                    "before_value": prev_val,
                    "min_value": curr_val,
                    "after_value": next_val,
                    "drop_magnitude": abs(change_to_curr)
                })

            # Check for suspicious spike (sharp rise followed by drop)
            elif change_to_curr > spike_threshold and change_from_curr < -spike_threshold * 0.5:
                suspicious_spikes.append({
                    "index": i,
                    "timestamp": samples[i]["timestamp"],
                    "before_value": prev_val,
                    "max_value": curr_val,
                    "after_value": next_val,
                    "spike_magnitude": change_to_curr
                })

        return {
            "suspicious_drops": suspicious_drops,
            "suspicious_spikes": suspicious_spikes,
            "total_suspicious": len(suspicious_drops) + len(suspicious_spikes)
        }

    def analyze_quality_flags(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze quality flags distribution.

        Args:
            samples: List of samples from the schema

        Returns:
            Dictionary with quality flag statistics
        """
        flag_counts = defaultdict(int)
        flagged_samples = 0

        for sample in samples:
            if "quality_flags" in sample and sample["quality_flags"]:
                flagged_samples += 1
                for flag in sample["quality_flags"]:
                    flag_counts[flag] += 1

        return {
            "total_flagged_samples": flagged_samples,
            "flagged_percentage": (flagged_samples / len(samples)) * 100 if samples else 0,
            "flag_breakdown": dict(flag_counts)
        }

    def generate_report(self, schema_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate complete sanity report.

        Args:
            schema_data: CGM time series schema data

        Returns:
            Dictionary containing the full sanity report
        """
        samples = schema_data.get("samples", [])
        unit = schema_data.get("unit", "mg/dL")
        sampling_interval = schema_data.get("sampling_interval_minutes", 5.0)

        if not samples:
            raise ValueError("No samples found in schema data")

        report = {
            "report_version": "1.0.0",
            "series_metadata": {
                "series_id": schema_data.get("series_id"),
                "subject_id": schema_data.get("subject_id"),
                "device_id": schema_data.get("device_id"),
                "time_zone": schema_data.get("time_zone"),
                "unit": unit,
                "total_samples": len(samples),
                "start_time": samples[0]["timestamp"],
                "end_time": samples[-1]["timestamp"]
            },
            "coverage": self.calculate_coverage(samples, sampling_interval),
            "sampling_regularity": self.check_sampling_regularity(samples),
            "extreme_values": self.analyze_extreme_values(samples, unit),
            "suspicious_changes": self.detect_suspicious_changes(samples, unit),
            "quality_flags": self.analyze_quality_flags(samples)
        }

        return report

    def print_summary(self, report: Dict[str, Any]) -> None:
        """
        Print a human-readable summary of the sanity report.

        Args:
            report: The sanity report dictionary
        """
        import sys

        meta = report["series_metadata"]
        coverage = report["coverage"]
        regularity = report["sampling_regularity"]
        extremes = report["extreme_values"]
        susp = report["suspicious_changes"]
        flags = report["quality_flags"]

        print(f"CGM Signal Sanity Report", file=sys.stderr)
        print(f"========================", file=sys.stderr)
        print(f"Series: {meta['series_id']}", file=sys.stderr)
        print(f"Subject: {meta['subject_id']}", file=sys.stderr)
        print(f"Device: {meta['device_id']}", file=sys.stderr)
        print(f"Time Zone: {meta['time_zone']}", file=sys.stderr)
        print(f"Unit: {meta['unit']}", file=sys.stderr)
        print(f"Period: {meta['start_time']} to {meta['end_time']}", file=sys.stderr)
        print(f"Total Samples: {meta['total_samples']}", file=sys.stderr)

        print(f"\nCoverage Analysis", file=sys.stderr)
        print(f"-----------------", file=sys.stderr)
        print(f"Coverage: {coverage['coverage_percentage']:.1f}%", file=sys.stderr)
        print(f"Expected intervals: {coverage['total_intervals']}", file=sys.stderr)
        print(f"Missing intervals: {coverage['missing_intervals']}", file=sys.stderr)
        print(f"Large gaps (>1.5x interval): {coverage['large_gaps']}", file=sys.stderr)

        print(f"\nSampling Regularity", file=sys.stderr)
        print(f"-------------------", file=sys.stderr)
        print(f"Mean interval: {regularity['mean_interval_minutes']:.1f} minutes", file=sys.stderr)
        print(f"CV of intervals: {regularity['cv_interval']:.3f}", file=sys.stderr)
        print(f"Irregular intervals: {regularity['irregular_intervals']}", file=sys.stderr)
        print(f"Regularity: {'Good' if regularity['is_regular'] else 'Poor'}", file=sys.stderr)

        print(f"\nExtreme Values", file=sys.stderr)
        print(f"--------------", file=sys.stderr)
        print(f"Range: {extremes['min_value']:.1f} - {extremes['max_value']:.1f} {extremes['unit']}", file=sys.stderr)
        print(f"Mean: {extremes['mean_value']:.1f} {extremes['unit']}", file=sys.stderr)
        print(f"Extreme low (<{3 if extremes['unit'] == 'mmol/L' else 54}): {extremes['extreme_low']} "
              f"({extremes['extreme_low_percentage']:.1f}%)", file=sys.stderr)
        print(f"Extreme high (>{15 if extremes['unit'] == 'mmol/L' else 270}): {extremes['extreme_high']} "
              f"({extremes['extreme_high_percentage']:.1f}%)", file=sys.stderr)

        print(f"\nSuspicious Changes", file=sys.stderr)
        print(f"------------------", file=sys.stderr)
        print(f"Suspicious drops: {len(susp['suspicious_drops'])}", file=sys.stderr)
        print(f"Suspicious spikes: {len(susp['suspicious_spikes'])}", file=sys.stderr)
        print(f"Total suspicious changes: {susp['total_suspicious']}", file=sys.stderr)

        print(f"\nQuality Flags", file=sys.stderr)
        print(f"-------------", file=sys.stderr)
        print(f"Flagged samples: {flags['total_flagged_samples']} ({flags['flagged_percentage']:.1f}%)",
              file=sys.stderr)
        if flags['flag_breakdown']:
            print(f"Flag breakdown:", file=sys.stderr)
            for flag, count in flags['flag_breakdown'].items():
                print(f"  {flag}: {count}", file=sys.stderr)

        print(f"\nOverall Assessment", file=sys.stderr)
        print(f"------------------", file=sys.stderr)
        issues = []

        if coverage['coverage_percentage'] < 80:
            issues.append(f"Low coverage ({coverage['coverage_percentage']:.1f}%)")
        if not regularity['is_regular']:
            issues.append("Irregular sampling")
        if extremes['extreme_low_percentage'] > 5:
            issues.append(f"High extreme low values ({extremes['extreme_low_percentage']:.1f}%)")
        if extremes['extreme_high_percentage'] > 5:
            issues.append(f"High extreme high values ({extremes['extreme_high_percentage']:.1f}%)")
        if susp['total_suspicious'] > meta['total_samples'] * 0.02:  # >2% suspicious
            issues.append(f"Many suspicious changes ({susp['total_suspicious']})")

        if len(issues) == 0:
            print("✓ No major issues detected", file=sys.stderr)
        else:
            print(f"⚠ Issues detected: {', '.join(issues)}", file=sys.stderr)

        print(f"\n", file=sys.stderr)
