#!/usr/bin/env python3
"""
Tests for CGM Event Metrics Calculator

Test all metrics calculations with comprehensive scenarios.
"""

import unittest
import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cgm_metrics.event_metrics import CGMEventMetrics, CGMEventMetricsError


class TestBaselineGlucose(unittest.TestCase):
    """Test baseline glucose calculation."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_baseline_simple(self):
        """Test baseline calculation with simple data."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": [
                {
                    "timestamp": (base_time - timedelta(minutes=30)).isoformat(),
                    "glucose_value": 95.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=25)).isoformat(),
                    "glucose_value": 98.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=20)).isoformat(),
                    "glucose_value": 96.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=15)).isoformat(),
                    "glucose_value": 94.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=10)).isoformat(),
                    "glucose_value": 97.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=5)).isoformat(),
                    "glucose_value": 100.0
                }
            ]
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_baseline_glucose(cgm_data, event)

        self.assertEqual(result["event_id"], event["event_id"])
        self.assertEqual(result["metric_name"], "baseline_glucose")
        self.assertEqual(result["unit"], "mg/dL")
        self.assertIn("metric_version", result)

        expected_baseline = (95 + 98 + 96 + 94 + 97 + 100) / 6
        self.assertAlmostEqual(result["value"], expected_baseline, places=1)

        self.assertIn("window", result)
        self.assertIn("coverage_ratio", result)
        self.assertIn("quality_flags", result)
        self.assertIn("quality_summary", result)

    def test_baseline_no_data(self):
        """Test baseline calculation with no data in window."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": []
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        with self.assertRaises(CGMEventMetricsError):
            self.metrics.calculate_baseline_glucose(cgm_data, event)

    def test_baseline_partial_coverage(self):
        """Test baseline with partial data coverage."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": [
                {
                    "timestamp": (base_time - timedelta(minutes=30)).isoformat(),
                    "glucose_value": 95.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=20)).isoformat(),
                    "glucose_value": 96.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=10)).isoformat(),
                    "glucose_value": 97.0
                },
                {
                    "timestamp": (base_time - timedelta(minutes=5)).isoformat(),
                    "glucose_value": 100.0
                }
            ]
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_baseline_glucose(cgm_data, event)

        self.assertIn("low_coverage", result["quality_flags"])
        self.assertIn("missing_data", result["quality_flags"])

        coverage_summary = result["quality_summary"]
        self.assertEqual(coverage_summary["window_samples"], 4)
        self.assertEqual(coverage_summary["expected_samples"], 7)
        self.assertAlmostEqual(coverage_summary["coverage_percentage"], 57.1, places=1)


class TestDeltaPeak(unittest.TestCase):
    """Test ΔPeak (peak change) calculation."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_delta_peak_simple(self):
        """Test ΔPeak with a clear glucose rise and fall."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        for i in range(37):  # 3 hours of 5-minute samples
            timestamp = base_time + timedelta(minutes=i * 5)

            if i < 6:
                value = 95 + i * 0.5  # Pre-event baseline ~95
            elif i < 18:
                # Peak phase
                peak_value = 180
                phase_value = 95 + (peak_value - 95) * (i - 6) / 12
                value = phase_value
            else:
                # Recovery phase
                value = peak_value - (peak_value - 95) * (i - 18) / 18

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_delta_peak(cgm_data, event)

        self.assertEqual(result["metric_name"], "delta_peak")
        self.assertGreater(result["value"], 80)  # Peak should be substantial
        self.assertLess(result["value"], 100)

        summary = result["quality_summary"]
        self.assertIn("peak_glucose", summary)
        self.assertIn("baseline_glucose", summary)
        self.assertIn("peak_time", summary)

        baseline = summary["baseline_glucose"]
        peak = summary["peak_glucose"]
        self.assertAlmostEqual(result["value"], peak - baseline, places=1)


class TestIAUC(unittest.TestCase):
    """Test iAUC (incremental area under curve) calculation."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_iAUC_simple_triangle(self):
        """Test iAUC with triangular glucose excursion."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        baseline_glucose = 100

        for i in range(25):
            timestamp = base_time + timedelta(minutes=i * 5)

            if i < 6:
                value = baseline_glucose
            elif i < 13:
                value = baseline_glucose + (i - 6) * 10
            else:
                time_down = i - 13
                value = baseline_glucose + 70 - time_down * 10

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_iAUC(cgm_data, event)

        self.assertEqual(result["metric_name"], "iAUC")
        self.assertIn("mg/dL * minutes", result["unit"])
        self.assertGreater(result["value"], 0)

        summary = result["quality_summary"]
        self.assertIn("baseline_glucose", summary)
        self.assertIn("positive_area", summary)

    def test_iAUC_no_rise(self):
        """Test iAUC when glucose doesn't rise above baseline."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        for i in range(13):
            timestamp = base_time + timedelta(minutes=i * 5)
            value = 100 + (i % 3) # Slight variation, no real rise

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_iAUC(cgm_data, event)

        # With no real rise above baseline, iAUC should be very small
        # (only counting positive differences from random minor variation)
        self.assertGreaterEqual(result["value"], 0)
        self.assertLess(result["value"], 100)


class TestTimeToPeak(unittest.TestCase):
    """Test time-to-peak calculation."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_time_to_peak(self):
        """Test time-to-peak with clear peak."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        for i in range(25):
            timestamp = base_time + timedelta(minutes=i * 5)

            if i < 6:
                value = 95 + i * 2  # Rising
            elif i < 12:
                value = 107 + (12 - i) * 10  # Peak
            else:
                value = 107 - (i - 12) * 2  # Falling

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_time_to_peak(cgm_data, event)

        self.assertEqual(result["metric_name"], "time_to_peak")
        self.assertEqual(result["unit"], "minutes")
        self.assertGreater(result["value"], 0)
        self.assertLess(result["value"], 120)

        summary = result["quality_summary"]
        self.assertIn("peak_glucose", summary)
        self.assertIn("peak_time", summary)

        peak_time = datetime.fromisoformat(summary["peak_time"])
        expected_time = (peak_time - base_time).total_seconds() / 60.0
        self.assertAlmostEqual(result["value"], expected_time, places=1)


class TestRecoverySlope(unittest.TestCase):
    """Test recovery slope calculation."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_recovery_slope(self):
        """Test recovery slope with clear recovery pattern."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        baseline = 100
        peak_value = 200

        # 6 pre-event samples
        for i in range(6):
            timestamp = base_time + timedelta(minutes=i * 5)
            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": baseline
            })

        # Peak samples (rapid rise)
        for i in range(7):
            timestamp = base_time + timedelta(minutes=(6 + i) * 5)
            value = baseline + (peak_value - baseline) * i / 6
            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        # Recovery samples (slow decline)
        for i in range(13):
            timestamp = base_time + timedelta(minutes=(13 + i) * 5)
            decline = (peak_value - baseline) * (i / 12)
            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": peak_value - decline
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_recovery_slope(cgm_data, event)

        self.assertEqual(result["metric_name"], "recovery_slope")
        self.assertIn("mg/dL per minute", result["unit"])

        summary = result["quality_summary"]
        self.assertIn("peak_glucose", summary)
        self.assertIn("recovery_start", summary)
        self.assertIn("recovery_end", summary)

        # Recovery slope should be negative (declining glucose)
        self.assertLess(result["value"], 0)

    def test_recovery_slope_no_recovery(self):
        """Test recovery slope with no recovery phase."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []

        # Continuous rise without recovery - need enough samples to cover recovery window
        for i in range(75):
            timestamp = base_time + timedelta(minutes=i * 5)
            value = 100 + i * 2  # Sustained rise
            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        result = self.metrics.calculate_recovery_slope(cgm_data, event)

        # No recovery should give positive slope (continuing to rise)
        self.assertGreater(result["value"], 0)


class TestCalculateAllMetrics(unittest.TestCase):
    """Test calculating all metrics for an event."""

    def setUp(self):
        self.metrics = CGMEventMetrics()

    def test_calculate_all_metrics_complete(self):
        """Test calculating all metrics with complete data."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = []
        baseline = 100
        peak_value = 180

        for i in range(50):
            timestamp = base_time + timedelta(minutes=i * 5)

            if i < 6:
                value = baseline
            elif i < 18:
                value = baseline + (peak_value - baseline) * (i - 6) / 12
            elif i < 30:
                value = peak_value - (peak_value - baseline) * (i - 18) / 12
            else:
                value = baseline + (i % 5)

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        metrics = self.metrics.calculate_all_metrics(cgm_data, event)

        metric_names = [m["metric_name"] for m in metrics]

        self.assertIn("baseline_glucose", metric_names)
        self.assertIn("delta_peak", metric_names)
        self.assertIn("iAUC", metric_names)
        self.assertIn("time_to_peak", metric_names)
        self.assertIn("recovery_slope", metric_names)

        # Check that all metrics have required metadata
        for metric in metrics:
            self.assertIn("event_id", metric)
            self.assertIn("metric_version", metric)
            self.assertIn("window", metric)
            self.assertIn("value", metric)
            self.assertIn("unit", metric)
            self.assertIn("coverage_ratio", metric)
            self.assertIn("quality_flags", metric)

    def test_calculate_all_metrics_insufficient_data(self):
        """Test calculating all metrics with insufficient data."""
        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        samples = [
            {
                "timestamp": (base_time + timedelta(minutes=10)).isoformat(),
                "glucose_value": 100
            }
        ]

        cgm_data = {
            "series_id": "test_series",
            "subject_id": "test_subject",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        event = {
            "event_id": "test_event",
            "event_type": "meal",
            "start_time": base_time.isoformat(),
            "source": "manual"
        }

        # Should handle gracefully with warnings logged
        metrics = self.metrics.calculate_all_metrics(cgm_data, event)

        # Most metrics should fail but not crash
        self.assertLess(len(metrics), 5)


class TestCLIWorkflow(unittest.TestCase):
    """Test end-to-end CLI workflow."""

    def setUp(self):
        pass

    def test_complete_cli_workflow(self):
        """Test complete workflow from files to metrics output."""
        from cgm_metrics.cli import calculate_event_metrics

        base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

        # Create CGM data
        samples = []
        baseline = 95
        peak_value = 160

        for i in range(50):
            timestamp = base_time + timedelta(minutes=i * 5)

            if i < 6:
                value = baseline
            elif i < 18:
                value = baseline + (peak_value - baseline) * (i - 6) / 12
            elif i < 30:
                value = peak_value - (peak_value - baseline) * (i - 18) / 12
            else:
                value = baseline + (i % 4)

            samples.append({
                "timestamp": timestamp.isoformat(),
                "glucose_value": value
            })

        cgm_data = {
            "schema_version": "1.0.0",
            "series_id": "test_series_cli",
            "subject_id": "test_subject_cli",
            "device_id": "test_device",
            "time_zone": "UTC",
            "unit": "mg/dL",
            "sampling_interval_minutes": 5.0,
            "samples": samples
        }

        # Create events data
        events_data = {
            "schema_version": "1.0.0",
            "events_id": "test_events_cli",
            "subject_id": "test_subject_cli",
            "time_zone": "UTC",
            "events": [
                {
                    "event_id": "meal_1",
                    "event_type": "meal",
                    "start_time": base_time.isoformat(),
                    "label": "test meal",
                    "source": "manual"
                }
            ]
        }

        metrics = calculate_event_metrics(
            cgm_data,
            events_data,
            "test_metrics_set"
        )

        # Verify schema compliance
        self.assertEqual(metrics["schema_version"], "1.0.0")
        self.assertEqual(metrics["metric_set_id"], "test_metrics_set")
        self.assertEqual(metrics["subject_id"], "test_subject_cli")
        self.assertEqual(metrics["time_zone"], "UTC")
        self.assertEqual(metrics["series_id"], "test_series_cli")
        self.assertIn("generated_at", metrics)
        self.assertIn("metrics", metrics)

        self.assertGreater(len(metrics["metrics"]), 0)

        for metric in metrics["metrics"]:
            self.assertIn("event_id", metric)
            self.assertIn("metric_name", metric)
            self.assertIn("window", metric)
            self.assertIn("value", metric)
            self.assertIn("unit", metric)
            self.assertIn("coverage_ratio", metric)


if __name__ == "__main__":
    unittest.main()
