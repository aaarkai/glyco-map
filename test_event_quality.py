#!/usr/bin/env python3
"""
Tests for event quality evaluation.
"""

import unittest
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from cgm_events.event_quality import EventQualityEvaluator


class TestEventQuality(unittest.TestCase):
    """Test event quality evaluation functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.evaluator = EventQualityEvaluator()
        self.test_timezone = "America/Los_Angeles"
        self.base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

    def create_test_cgm_data(self, start_time, sample_count, interval_minutes=5):
        """Create test CGM data."""
        samples = []
        for i in range(sample_count):
            timestamp = start_time + timedelta(minutes=i * interval_minutes)
            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": 100 + (i % 10),
                "sample_index": i
            })

        return {
            "schema_version": "1.0.0",
            "series_id": "test_cgm",
            "subject_id": "test_subject",
            "device_id": "test_device",
            "time_zone": "UTC",
            "unit": "mg/dL",
            "sampling_interval_minutes": interval_minutes,
            "samples": samples
        }

    def create_test_event(self, start_offset_minutes, duration_minutes=None, label="Test event"):
        """Create a test event."""
        start_time = self.base_time + timedelta(minutes=start_offset_minutes)

        event = {
            "event_id": f"evt_test_{start_offset_minutes}",
            "event_type": "meal",
            "start_time": start_time.isoformat(),
            "source": "manual",
            "annotation_quality": 0.8,
            "label": label
        }

        if duration_minutes:
            end_time = start_time + timedelta(minutes=duration_minutes)
            event["end_time"] = end_time.isoformat()

        return event

    def test_cgm_overlap_complete(self):
        """Test CGM overlap with complete coverage."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        event = self.create_test_event(30, duration_minutes=30)  # 30-60 min

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        overlap = self.evaluator.check_cgm_overlap(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertTrue(overlap['has_overlap'])
        self.assertAlmostEqual(overlap['coverage_fraction'], 1.0, places=1)
        self.assertEqual(overlap['issues'], [])

    def test_cgm_overlap_partial(self):
        """Test CGM overlap with partial coverage."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        # Event after CGM data ends (CGM ends at 8:00 + 100*5min = 16:20)
        # Event at 20 hours (14 hours after CGM ends)
        far_time = datetime(2024, 1, 2, 4, 0, tzinfo=timezone.utc)  # Next day 4am
        event = {
            "event_id": "evt_far",
            "event_type": "meal",
            "start_time": far_time.isoformat(),
            "source": "manual"
        }

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        overlap = self.evaluator.check_cgm_overlap(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertFalse(overlap['has_overlap'])

    def test_cgm_overlap_with_gaps(self):
        """Test CGM overlap with gaps during event."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        # Remove some samples to create gaps
        del cgm_data['samples'][10:15]  # 25-minute gap
        del cgm_data['samples'][20:25]  # Another 25-minute gap

        event = self.create_test_event(0, duration_minutes=120)  # 2 hour event

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        overlap = self.evaluator.check_cgm_overlap(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertTrue(overlap['has_overlap'])
        self.assertLess(overlap['coverage_fraction'], 0.9)
        self.assertGreater(overlap['gap_count'], 0)

    def test_event_isolation_isolated(self):
        """Test event isolation with no nearby events."""
        events = [
            self.create_test_event(0, duration_minutes=30, label="Breakfast"),
            self.create_test_event(300, duration_minutes=30, label="Lunch"),  # 5 hours later
            self.create_test_event(600, duration_minutes=30, label="Dinner")  # 5 hours later
        ]

        isolation = self.evaluator.check_event_isolation(events[0], events)

        self.assertTrue(isolation['is_isolated'])
        self.assertEqual(isolation['overlapping_events'], [])
        self.assertGreater(isolation['nearest_event_gap_minutes'], 200)

    def test_event_isolation_with_overlap(self):
        """Test event isolation with overlapping events."""
        events = [
            self.create_test_event(0, duration_minutes=60, label="Meal 1"),
            self.create_test_event(30, duration_minutes=60, label="Meal 2")  # Overlaps
        ]

        isolation = self.evaluator.check_event_isolation(events[0], events)

        self.assertFalse(isolation['is_isolated'])
        self.assertEqual(len(isolation['overlapping_events']), 1)
        self.assertEqual(isolation['overlapping_events'][0]['label'], "Meal 2")

    def test_event_isolation_close_events(self):
        """Test event isolation with close but non-overlapping events."""
        events = [
            self.create_test_event(0, duration_minutes=30, label="Meal 1"),
            self.create_test_event(45, duration_minutes=30, label="Meal 2")  # Only 15 min gap
        ]

        isolation = self.evaluator.check_event_isolation(events[0], events)

        self.assertTrue(isolation['is_isolated'])  # No overlap
        self.assertEqual(len(isolation['overlapping_events']), 0)
        self.assertLess(isolation['nearest_event_gap_minutes'], 20)
        self.assertIn('Close to other events', '\n'.join(isolation['issues']))

    def test_pre_event_baseline_sufficient(self):
        """Test pre-event baseline with sufficient coverage."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        event = self.create_test_event(60, duration_minutes=30)  # Event at 60 min

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        baseline = self.evaluator.check_pre_event_baseline(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertTrue(baseline['has_sufficient_baseline'])
        self.assertGreaterEqual(baseline['coverage_fraction'], 0.9)
        self.assertEqual(baseline['issues'], [])

    def test_pre_event_baseline_insufficient(self):
        """Test pre-event baseline with insufficient coverage."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        # Remove samples before event to create insufficient baseline
        cgm_data['samples'] = cgm_data['samples'][50:]  # Start at 250 minutes

        event = self.create_test_event(60, duration_minutes=30)  # Event at 60 min

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        baseline = self.evaluator.check_pre_event_baseline(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertFalse(baseline['has_sufficient_baseline'])
        self.assertLess(baseline['coverage_fraction'], 0.5)
        self.assertGreater(len(baseline['issues']), 0)

    def test_pre_event_baseline_with_gaps(self):
        """Test pre-event baseline with large gaps."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)
        # Remove only 1 sample to create a 10 minute gap (2 intervals) but keep coverage high
        # This tests gap detection without failing coverage thresholds
        del cgm_data['samples'][10:11]

        event = self.create_test_event(90, duration_minutes=30)

        cgm_timestamps = self.evaluator.parse_cgm_timestamps(cgm_data)
        baseline = self.evaluator.check_pre_event_baseline(
            event, cgm_timestamps, cgm_data['sampling_interval_minutes']
        )

        self.assertTrue(baseline['has_sufficient_baseline'])
        # Gap should be detected (10+ minutes)
        self.assertGreaterEqual(baseline['max_gap_minutes'], 10)

    def test_complete_evaluation_with_cgm(self):
        """Test complete event quality evaluation with CGM data."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)

        events_data = {
            'schema_version': '1.0.0',
            'events_id': 'test_events',
            'subject_id': 'test_subject',
            'time_zone': 'UTC',
            'events': [
                self.create_test_event(30, duration_minutes=30, label="Good event"),
                self.create_test_event(200, duration_minutes=30, label="Event after gap")
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(cgm_data, f)
            cgm_file = f.name

        try:
            evaluation = self.evaluator.evaluate_all_events(events_data, cgm_file)

            self.assertEqual(evaluation['total_events'], 2)
            self.assertEqual(evaluation['usable_events'], 2)
            self.assertEqual(len(evaluation['evaluations']), 2)

            first_event = evaluation['evaluations'][0]
            self.assertEqual(first_event['event_id'], 'evt_test_30')
            self.assertTrue(first_event['is_usable_for_analysis'])

        finally:
            Path(cgm_file).unlink()

    def test_complete_evaluation_without_cgm(self):
        """Test complete event quality evaluation without CGM data."""
        events_data = {
            'schema_version': '1.0.0',
            'events_id': 'test_events',
            'subject_id': 'test_subject',
            'time_zone': 'UTC',
            'events': [
                self.create_test_event(30, duration_minutes=30, label="Event")
            ]
        }

        evaluation = self.evaluator.evaluate_all_events(events_data)

        self.assertEqual(evaluation['total_events'], 1)
        self.assertEqual(evaluation['usable_events'], 0)  # No CGM = not usable
        self.assertEqual(len(evaluation['evaluations']), 1)

        event_eval = evaluation['evaluations'][0]
        self.assertFalse(event_eval['is_usable_for_analysis'])
        # Without CGM, should have issues
        self.assertTrue(len(event_eval['quality_issues']) > 0)

    def test_quality_score_calculation(self):
        """Test quality score calculation."""
        cgm_data = self.create_test_cgm_data(self.base_time, 100)

        # Create event that should have multiple issues
        event = self.create_test_event(10, duration_minutes=30, label="Problematic event")
        events = [
            event,
            self.create_test_event(25, duration_minutes=30, label="Overlapping event")
            # Overlaps with first event
        ]

        evaluation = self.evaluator.evaluate_event_quality(event, events, cgm_data)

        self.assertLess(evaluation['quality_score'], 1.0)
        self.assertGreater(len(evaluation['quality_issues']), 0)

    def test_empty_events(self):
        """Test evaluation with no events."""
        events_data = {
            'schema_version': '1.0.0',
            'events_id': 'empty_events',
            'subject_id': 'test_subject',
            'time_zone': 'UTC',
            'events': []
        }

        evaluation = self.evaluator.evaluate_all_events(events_data)

        self.assertEqual(evaluation['total_events'], 0)
        self.assertEqual(evaluation['evaluations'], [])


def run_tests():
    """Run the test suite."""
    unittest.main(verbosity=2)


if __name__ == "__main__":
    run_tests()
