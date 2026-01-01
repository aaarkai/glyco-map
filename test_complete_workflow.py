#!/usr/bin/env python3
"""
Complete workflow test demonstrating CGM import and event creation.
"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

def test_complete_workflow():
    """Test complete workflow from CGM import to event creation."""
    print("Testing Complete CGM Workflow")
    print("=" * 60)

    # 1. Simulate CGM import (we'd normally read from XLSX)
    print("\n1. Simulating CGM data import...")
    from cgm_importer.importer import CGM_XLSX_Importer
    importer = CGM_XLSX_Importer()

    # Create sample CGM data
    cgm_samples = []
    base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
    for i in range(48):  # 4 hours of 5-minute samples
        timestamp = base_time + timedelta(minutes=i*5)
        # Simulate glucose rise and fall
        if i < 12:
            glucose = 95 + i*2  # Rising
        elif i < 24:
            glucose = 120 - (i-12)*1.5  # Falling
        else:
            glucose = 95 + (i % 5)  # Stable with minor variation

        cgm_samples.append({
            "timestamp": timestamp.isoformat(),
            "glucose_value": glucose,
            "sample_index": i
        })

    cgm_data = {
        "schema_version": "1.0.0",
        "series_id": "test_cgm_series",
        "subject_id": "subject_workflow_test",
        "device_id": "test_cgm_device",
        "time_zone": "UTC",
        "unit": "mg/dL",
        "sampling_interval_minutes": 5.0,
        "samples": cgm_samples
    }

    print(f"   Imported {len(cgm_samples)} CGM samples")
    print(f"   Time range: {cgm_samples[0]['timestamp']} to {cgm_samples[-1]['timestamp']}")

    # 2. Generate sanity report
    print("\n2. Generating signal sanity report...")
    from cgm_importer.sanity_report import CGMSanityReport
    reporter = CGMSanityReport()

    report = reporter.generate_report(cgm_data)
    print(f"   Coverage: {report['coverage']['coverage_percentage']:.1f}%")
    print(f"   Mean glucose: {report['extreme_values']['mean_value']:.1f} mg/dL")
    print(f"   Range: {report['extreme_values']['min_value']:.1f} - {report['extreme_values']['max_value']:.1f} mg/dL")

    # 3. Create meal events
    print("\n3. Creating meal event annotations...")
    from cgm_events.events import CGMEventCreator
    creator = CGMEventCreator()

    events = []

    # Breakfast event
    breakfast = creator.create_event(
        subject_id="subject_workflow_test",
        event_type="meal",
        start_time=base_time + timedelta(hours=-1),  # 7 AM
        label="oatmeal breakfast",
        estimated_carbs=45.0,
        context_tags=["breakfast", "home_cooked"],
        source="manual",
        annotation_quality=0.9
    )
    events.append(breakfast)
    print(f"   Created breakfast: {breakfast['label']}")

    # Lunch event
    lunch = creator.create_event(
        subject_id="subject_workflow_test",
        event_type="meal",
        start_time=base_time + timedelta(hours=4),  # 12 PM
        end_time=base_time + timedelta(hours=4, minutes=30),
        label="sandwich lunch",
        estimated_carbs=60.0,
        context_tags=["lunch", "packaged"],
        source="manual",
        annotation_quality=0.8
    )
    events.append(lunch)
    print(f"   Created lunch: {lunch['label']}")

    # Create events collection
    events_data = creator.create_events_collection(
        subject_id="subject_workflow_test",
        timezone="UTC",
        events=events,
        collection_notes="Testing complete workflow"
    )

    print(f"   Total events created: {len(events)}")

    # 4. Validate events
    print("\n4. Validating event annotations...")
    for event in events:
        warnings = creator.validate_event(event)
        if warnings:
            print(f"   ⚠ {event['event_type']}: {len(warnings)} warnings")
            for warning in warnings:
                print(f"     - {warning}")
        else:
            print(f"   ✓ {event['event_type']}: No warnings")

    # 5. Write to files
    print("\n5. Writing data to files...")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write CGM data
        cgm_file = Path(tmpdir) / "cgm_data.json"
        with open(cgm_file, 'w') as f:
            json.dump(cgm_data, f, indent=2)
        print(f"   Wrote CGM data: {cgm_file}")

        # Write events
        events_file = Path(tmpdir) / "events.json"
        with open(events_file, 'w') as f:
            json.dump(events_data, f, indent=2)
        print(f"   Wrote events: {events_file}")

        # Verify files
        cgm_size = cgm_file.stat().st_size
        events_size = events_file.stat().st_size
        print(f"   File sizes: CGM {cgm_size} bytes, Events {events_size} bytes")

    print("\n" + "=" * 60)
    print("✓ Complete workflow successful!")
    print("=" * 60)

    print("\nKey Points:")
    print("- CGM data: measurements with objective timestamps")
    print("- Events: claims about exposures with subjective quality")
    print("- Both are needed for causal analysis, but have different certainty")
    print("- Always validate event annotations before drawing conclusions")

if __name__ == "__main__":
    test_complete_workflow()
