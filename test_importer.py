#!/usr/bin/env python3
"""
Minimal test suite for CGM XLSX importer.
"""

import unittest
import tempfile
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from cgm_importer.importer import CGM_XLSX_Importer


class TestCGMImporter(unittest.TestCase):
    """Test CGM XLSX importer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.importer = CGM_XLSX_Importer()
        self.test_data_dir = Path("test_data")
        self.test_data_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.test_data_dir, ignore_errors=True)

    def create_test_xlsx(self, filename, data):
        """Create a test XLSX file with CGM data."""
        filepath = self.test_data_dir / filename
        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False)
        return filepath

    def test_read_xlsx_basic(self):
        """Test basic XLSX reading."""
        # Create test data
        timestamps = [datetime(2024, 1, 1, 8, 0) + timedelta(minutes=i*5) for i in range(10)]
        data = {
            "血糖时间": timestamps,
            "血糖值": [95, 98, 102, 105, 108, 110, 108, 105, 102, 98]
        }
        filepath = self.create_test_xlsx("test_basic.xlsx", data)

        # Test reading
        df = self.importer.read_xlsx(str(filepath))
        self.assertEqual(len(df), 10)
        self.assertIn("timestamp", df.columns)
        self.assertIn("glucose_value", df.columns)
        self.assertEqual(df.iloc[0]["glucose_value"], 95)

    def test_detect_sampling_interval_regular(self):
        """Test sampling interval detection for regular intervals."""
        # Create 5-minute interval data
        timestamps = pd.to_datetime([
            "2024-01-01 08:00",
            "2024-01-01 08:05",
            "2024-01-01 08:10",
            "2024-01-01 08:15",
            "2024-01-01 08:20",
            "2024-01-01 08:25",
        ])

        interval = self.importer.detect_sampling_interval(timestamps)
        self.assertAlmostEqual(interval, 5.0, places=1)

    def test_detect_sampling_interval_15min(self):
        """Test sampling interval detection for 15-minute intervals."""
        timestamps = pd.to_datetime([
            "2024-01-01 08:00",
            "2024-01-01 08:15",
            "2024-01-01 08:30",
            "2024-01-01 08:45",
            "2024-01-01 09:00",
        ])

        interval = self.importer.detect_sampling_interval(timestamps)
        self.assertAlmostEqual(interval, 15.0, places=1)

    def test_detect_sampling_interval_tolerant(self):
        """Test sampling interval detection with slight variations."""
        # Add some slight variation (not exact multiples)
        base = datetime(2024, 1, 1, 8, 0)
        timestamps = pd.to_datetime([base + timedelta(minutes=i*5 + (i%2)*0.5) for i in range(10)])

        interval = self.importer.detect_sampling_interval(timestamps)
        self.assertAlmostEqual(interval, 5.0, places=0)

    def test_detect_artifacts_rapid_changes(self):
        """Test artifact detection for rapid glucose jumps."""
        values = pd.Series([95, 98, 102, 98, 150, 100, 105, 108, 40, 98])
        flags = self.importer.detect_artifacts(values)

        # Sample 4 with rapid jump to 150 then back to 100 should be flagged
        self.assertIn("artifact", flags[4])

    def test_detect_artifacts_flat_readings(self):
        """Test artifact detection for flat readings."""
        values = pd.Series([98, 98, 98, 98, 99, 100, 101])
        flags = self.importer.detect_artifacts(values)

        # Samples 2 through 4 should be flagged as flat
        self.assertIn("artifact", flags[2])

    def test_detect_artifacts_flat_readings(self):
        """Test artifact detection for flat readings."""
        values = pd.Series([98, 98, 98, 98, 99, 100, 101])
        flags = self.importer.detect_artifacts(values)

        # Samples 2 through 4 should be flagged as flat
        self.assertIn("artifact", flags[2])

    def test_convert_to_schema_structure(self):
        """Test complete schema conversion."""
        # Create realistic test data
        timestamps = pd.to_datetime([
            f"2024-01-01 {8+i//12:02d}:{(i%12)*5:02d}:00"
            for i in range(24)
        ])
        values = [95 + np.sin(i/2)*5 for i in range(24)]  # Gentle oscillation

        df = pd.DataFrame({
            "timestamp": timestamps,
            "glucose_value": values
        })

        # Convert to schema
        schema = self.importer.convert_to_schema(
            df,
            subject_id="test-subject-1",
            device_id="test-device-1",
            timezone="America/Los_Angeles",
            unit="mg/dL"
        )

        # Verify schema structure
        self.assertEqual(schema["schema_version"], "1.0.0")
        self.assertEqual(schema["subject_id"], "test-subject-1")
        self.assertEqual(schema["device_id"], "test-device-1")
        self.assertEqual(schema["time_zone"], "America/Los_Angeles")
        self.assertEqual(schema["unit"], "mg/dL")
        self.assertEqual(len(schema["samples"]), 24)

        # Verify sample structure
        sample = schema["samples"][0]
        self.assertIn("timestamp", sample)
        self.assertIn("glucose_value", sample)
        self.assertIn("sample_index", sample)
        self.assertTrue(sample["timestamp"].endswith("-08:00"))  # LA timezone

    def test_missing_columns_error(self):
        """Test error handling for missing columns."""
        data = {
            "時間": [],  # Wrong column name
            "值": []
        }
        filepath = self.create_test_xlsx("test_missing.xlsx", data)

        with self.assertRaises(ValueError) as ctx:
            self.importer.read_xlsx(str(filepath))

        self.assertIn("Missing required columns", str(ctx.exception))

    def test_real_data_sample(self):
        """Test with a small realistic sample that mimics real CGM data."""
        # Create small dataset that represents a meal response
        base_time = datetime(2024, 1, 1, 18, 0)  # 6 PM

        timestamps = [base_time + timedelta(minutes=i*5) for i in range(24)]
        # Simulate glucose response to a meal
        baseline = 100
        glucose = [
            baseline, 98, 96, 95,  # pre-meal (4)
            98, 105, 125, 140, 160,  # rising (5)
            170, 175, 180, 178, 172,  # peak (5)
            165, 155, 145, 135,  # falling (4)
            128, 122, 115, 110, 108, 105,  # returning (6)
        ]

        data = {
            "血糖时间": timestamps,
            "血糖值": glucose
        }

        filepath = self.create_test_xlsx("test_meal.xlsx", data)

        # Process the file
        df = self.importer.read_xlsx(str(filepath))
        interval = self.importer.detect_sampling_interval(df["timestamp"])
        flags = self.importer.detect_artifacts(df["glucose_value"])

        # Verify results
        self.assertEqual(len(df), 24)
        self.assertAlmostEqual(interval, 5.0, places=1)
        # Realistic data shouldn't have many artifacts
        artifact_count = sum(1 for f in flags if "artifact" in f or "sensor_error" in f)
        self.assertLess(artifact_count, 3)

def run_tests():
    """Run the test suite."""
    unittest.main(verbosity=2)


if __name__ == "__main__":
    run_tests()
