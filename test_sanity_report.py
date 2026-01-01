#!/usr/bin/env python3
"""
Simple test for sanity report functionality.
"""

import json
import tempfile
from pathlib import Path
from cgm_importer.sanity_report import CGMSanityReport


def create_test_schema():
    """Create a test CGM schema for testing."""
    return {
        "schema_version": "1.0.0",
        "series_id": "test_series_001",
        "subject_id": "test_subject",
        "device_id": "test_device",
        "time_zone": "America/Los_Angeles",
        "unit": "mmol/L",
        "sampling_interval_minutes": 5.0,
        "samples": [
            {
                "timestamp": "2025-01-01T08:00:00Z",
                "glucose_value": 5.5,
                "sample_index": 0
            },
            {
                "timestamp": "2025-01-01T08:05:00Z",
                "glucose_value": 5.8,
                "sample_index": 1
            },
            {
                "timestamp": "2025-01-01T08:10:00Z",
                "glucose_value": 6.2,
                "sample_index": 2
            },
            {
                "timestamp": "2025-01-01T08:15:00Z",
                "glucose_value": 10.5,  # Spike
                "sample_index": 3
            },
            {
                "timestamp": "2025-01-01T08:20:00Z",
                "glucose_value": 6.0,
                "sample_index": 4
            },
            {
                "timestamp": "2025-01-01T08:40:00Z",  # Gap
                "glucose_value": 5.5,
                "sample_index": 5
            },
            {
                "timestamp": "2025-01-01T08:45:00Z",
                "glucose_value": 5.5,
                "sample_index": 6
            },
            {
                "timestamp": "2025-01-01T08:50:00Z",
                "glucose_value": 2.5,  # Low value
                "sample_index": 7
            }
        ]
    }


def test_sanity_report():
    """Test the complete sanity report generation."""
    print("Testing CGMSanityReport...")

    # Create reporter
    reporter = CGMSanityReport()

    # Create test data
    schema = create_test_schema()

    # Generate report
    report = reporter.generate_report(schema)

    # Check report structure
    assert "report_version" in report
    assert "series_metadata" in report
    assert "coverage" in report
    assert "sampling_regularity" in report
    assert "extreme_values" in report
    assert "suspicious_changes" in report
    assert "quality_flags" in report

    print("✓ Report structure is correct")

    # Check metadata
    meta = report["series_metadata"]
    assert meta["series_id"] == "test_series_001"
    assert meta["subject_id"] == "test_subject"
    assert meta["total_samples"] == 8

    print("✓ Metadata is correct")

    # Check coverage
    coverage = report["coverage"]
    assert coverage["total_intervals"] == 10  # 50 minutes / 5 minute intervals
    assert coverage["missing_intervals"] == 3  # 3 missing intervals
    assert coverage["large_gaps"] == 1  # One 20-minute gap

    print("✓ Coverage calculation is correct")

    # Check extreme values
    extremes = report["extreme_values"]
    assert extremes["min_value"] == 2.5
    assert extremes["max_value"] == 10.5
    assert extremes["extreme_low"] == 1  # One value < 3 mmol/L

    print("✓ Extreme values are correct")

    # Check suspicious changes
    susp = report["suspicious_changes"]
    assert "suspicious_spikes" in susp

    print("✓ Suspicious changes detection is working")

    # Test JSON serialization
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(report, f, indent=2)
        temp_file = f.name

    # Load it back
    with open(temp_file, 'r') as f:
        loaded_report = json.load(f)

    assert loaded_report["series_metadata"]["series_id"] == "test_series_001"

    print("✓ Report is JSON serializable")

    # Cleanup
    Path(temp_file).unlink()

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_sanity_report()
