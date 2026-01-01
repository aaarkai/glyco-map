#!/usr/bin/env python3
"""
Complete Demo: CGM Import -> Events -> Metrics

This script demonstrates a complete workflow:
1. Load CGM data (simulates XLSX import)
2. Create meal events
3. Calculate per-event windowed metrics

Key Features:
- Each metric includes window definition, coverage ratio, and version
- Metrics are computed relative to event start times
- Coverage warnings help identify unreliable metrics
"""

import json
from datetime import datetime, timezone, timedelta
from cgm_events.events import CGMEventCreator
from cgm_metrics.cli import calculate_event_metrics


def simulate_cgm_import():
    """Simulate importing CGM data (normally from XLSX)."""
    print("1. Simulating CGM Data Import")
    print("-" * 60)

    # Create 12 hours of realistic CGM data
    base_time = datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc)
    samples = []

    for i in range(144):  # 12 hours at 5-minute intervals
        timestamp = base_time + timedelta(minutes=i * 5)

        # Simulate glucose pattern with meals
        if i < 60:  # 7-12 AM: fasting baseline
            glucose = 92 + (i % 4)
        elif i < 72:  # 12-1 PM: lunch rise
            # Rise from ~95 to ~165 over 60 minutes
            rise = min((i - 60) * 5, 70)
            glucose = 95 + rise
        elif i < 84:  # 1-2 PM: lunch recovery
            recovery = min((i - 72) * 3, 35)
            glucose = 165 - recovery
        elif i < 84:  # 2-7 PM: afternoon baseline
            glucose = 100 + (i % 5)
        elif i < 96:  # 7-8 PM: dinner rise
            rise = min((i - 96) * 4, 80)
            glucose = 95 + rise
        elif i < 108:  # 8-9 PM: dinner recovery
            recovery = min((i - 96) * 4, 40)
            glucose = 175 - recovery
        else:  # Evening baseline
            glucose = 100 + (i % 4)

        samples.append({
            "timestamp": timestamp.isoformat(),
            "glucose_value": glucose,
            "sample_index": i
        })

    cgm_data = {
        "schema_version": "1.0.0",
        "series_id": "demo_cgm_series_1",
        "subject_id": "demo_subject_1",
        "device_id": "demo_cgm_001",
        "time_zone": "America/Los_Angeles",
        "unit": "mg/dL",
        "sampling_interval_minutes": 5.0,
        "samples": samples
    }

    print(f"   Imported {len(samples)} CGM samples")
    print(f"   Time range: {samples[0]['timestamp']} to {samples[-1]['timestamp']}")
    print(f"   Subject: {cgm_data['subject_id']}")
    print(f"   Device: {cgm_data['device_id']}")

    return cgm_data


def create_meal_events():
    """Create meal events for metrics calculation."""
    print("\n2. Creating Meal Events")
    print("-" * 60)

    base_time = datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc)
    creator = CGMEventCreator()

    events = []

    # Lunch event
    lunch_start = base_time + timedelta(hours=5)  # 12:00 PM
    lunch = creator.create_event(
        subject_id="demo_subject_1",
        event_type="meal",
        start_time=lunch_start,
        end_time=lunch_start + timedelta(minutes=45),
        label="lunch - pasta",
        estimated_carbs=65,
        context_tags=["lunch", "restaurant"],
        source="manual",
        annotation_quality=0.85,
        notes="Ate at Italian restaurant, estimated portions"
    )
    events.append(lunch)
    print(f"   ✓ Lunch: {lunch['label']}")
    print(f"     Time: {lunch['start_time']}")
    print(f"     Carbs: {lunch['exposure_components'][0]['value']}g")
    print(f"     Quality: {lunch['annotation_quality'] * 100:.0f}%")

    # Dinner event
    dinner_start = base_time + timedelta(hours=12)  # 7:00 PM
    dinner = creator.create_event(
        subject_id="demo_subject_1",
        event_type="meal",
        start_time=dinner_start,
        end_time=dinner_start + timedelta(minutes=60),
        label="dinner - stir fry",
        estimated_carbs=55,
        context_tags=["dinner", "home_cooked"],
        source="manual",
        annotation_quality=0.90,
        notes="Chicken with mixed vegetables and rice"
    )
    events.append(dinner)
    print(f"   ✓ Dinner: {dinner['label']}")
    print(f"     Time: {dinner['start_time']}")
    print(f"     Carbs: {dinner['exposure_components'][0]['value']}g")
    print(f"     Quality: {dinner['annotation_quality'] * 100:.0f}%")

    # Create events collection
    events_data = creator.create_events_collection(
        subject_id="demo_subject_1",
        timezone="America/Los_Angeles",
        events=events,
        collection_notes="Demo: lunch and dinner on Jan 1, 2024"
    )

    print(f"\n   Total events: {len(events)}")

    return events_data


def calculate_metrics(cgm_data, events_data):
    """Calculate all event-windowed metrics."""
    print("\n3. Calculating Event Metrics")
    print("-" * 60)

    metrics = calculate_event_metrics(
        cgm_data,
        events_data,
        "demo_metrics_set_1",
        verbose=True
    )

    return metrics


def analyze_metrics(metrics):
    """Analyze and display metrics results."""
    print("\n4. Metrics Analysis")
    print("-" * 60)

    # Group metrics by event
    events_metrics = {}
    for metric in metrics['metrics']:
        event_id = metric['event_id']
        if event_id not in events_metrics:
            events_metrics[event_id] = []
        events_metrics[event_id].append(metric)

    for event_id, event_metrics in events_metrics.items():
        print(f"\n   Event: {event_id}")

        for metric in event_metrics:
            metric_name = metric['metric_name']
            value = metric['value']
            unit = metric['unit']
            coverage = metric['quality_summary'].get('coverage_percentage', 0)

            # Format based on metric type
            if metric_name == 'baseline_glucose':
                print(f"      {metric_name}: {value:.1f} {unit} (coverage: {coverage:.0f}%)")
            elif metric_name == 'delta_peak':
                baseline = metric['quality_summary']['baseline_glucose']
                peak = metric['quality_summary']['peak_glucose']
                print(f"      {metric_name}: {value:.1f} {unit} (peak={peak:.1f}, baseline={baseline:.1f})")
            elif metric_name == 'iAUC':
                baseline = metric['quality_summary']['baseline_glucose']
                print(f"      {metric_name}: {value:.1f} {unit} (baseline={baseline:.1f} mg/dL)")
            elif metric_name == 'time_to_peak':
                peak_time = metric['quality_summary']['peak_time']
                print(f"      {metric_name}: {value:.1f} {unit} (at: {peak_time})")
            elif metric_name == 'recovery_slope':
                return_pct = metric['quality_summary']['return_toward_baseline_percentage']
                if return_pct:
                    print(f"      {metric_name}: {value:.2f} {unit} (return: {return_pct:.1f}%)")
                else:
                    print(f"      {metric_name}: {value:.2f} {unit}")

            # Flag low coverage
            if coverage < 70:
                print(f"           ⚠ Warning: Low coverage - metrics may be unreliable")


def print_tutorial():
    """Print tutorial explaining the metrics."""
    print("\n" + "=" * 60)
    print("TUTORIAL: Understanding Event Metrics")
    print("=" * 60)

    tutorial = """
Key Concepts
------------

1. EVENTS ARE CLAIMS, NOT MEASUREMENTS
   - Events (meals, interventions) are subject-reported
   - Annotation quality affects metric reliability
   - Always validate event metadata before drawing conclusions

2. WINDOWED METRICS
   All metrics are calculated within specific time windows:
   - Baseline: typically [-30, 0] minutes before event
   - Post-event: typically [0, 180] minutes after event
   - Recovery: typically [120, 240] minutes after event

3. COVERAGE RATIO
   Each metric includes the proportion of expected samples that were available:
   - 100%: All samples present in window
   - 70%+: Acceptable for most analyses
   - <70%: Should consider excluding or flagging as unreliable

4. COMPUTATION VERSIONS
   Each metric includes a version number (e.g., "1.0.0") to ensure reproducibility.
   Update version when computation logic changes.

Metrics Explained
-----------------

baseline_glucose: Mean glucose before event
   Uses: Establish baseline for change calculations
   Unit: mg/dL (or mmol/L)

ΔPeak (delta_peak): Peak glucose change from baseline
   Calculation: peak_glucose - baseline_glucose
   Uses: Assess maximum glycemic impact
   Unit: mg/dL (or mmol/L)

iAUC (incremental AUC): Area above baseline over time
   Calculation: Π(glucose - baseline) × time using trapezoid rule
   Uses: Quantify total glycemic exposure
   Unit: mg/dL × minutes

time_to_peak: Time from event start to peak glucose
   Calculation: peak_timestamp - event_start
   Uses: Assess speed of glucose response
   Unit: minutes

recovery_slope: Rate of glucose decline after peak
   Calculation: Linear regression slope in recovery window
   Positive: Declining glucose (recovering)
   Negative: Continuous rise (no recovery)
   Unit: mg/dL per minute

Quality Considerations
----------------------

⚠ Low Coverage (<70%): Insufficient data for reliable metrics
⚠ Annotation Quality: Low quality events may have:
    - Wrong timing (recall bias)
    - Wrong carb estimates
    - Missing context (exercise, stress, illness)
⚠ Sensor Issues: Artifacts (rapid jumps) or sensor errors can distort metrics

Best Practices
--------------

1. Always check coverage before analyzing metrics
2. Cross-validate event quality with subject notes
3. Compare metrics across similar events (same meal type, time)
4. Examine plots of CGM data around events for sanity checking
5. Use metrics to generate hypotheses, not definitive conclusions
"""

    print(tutorial)


def main():
    """Run complete demo workflow."""
    print("=" * 60)
    print("CGM EVENT METRICS - COMPLETE DEMO")
    print("=" * 60)

    # Run workflow
    cgm_data = simulate_cgm_import()
    events_data = create_meal_events()
    metrics = calculate_metrics(cgm_data, events_data)

    # Analyze results
    analyze_metrics(metrics)

    # Print comprehensive tutorial
    response = input("\nShow detailed tutorial? (y/N): ")
    if response.lower() == 'y':
        print_tutorial()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)

    print("\nNext Steps:")
    print("1. Review metrics for each event")
    print("2. Check coverage ratios (aim for >70%)")
    print("3. Examine plots to validate patterns")
    print("4. Compare metrics across similar events")
    print("5. Generate hypotheses for further testing")


if __name__ == "__main__":
    main()
