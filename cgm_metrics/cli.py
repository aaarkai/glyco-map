"""
CLI for CGM Event Metrics Calculation

Calculate windowed metrics for CGM events from command line.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from .event_metrics import CGMEventMetrics


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load JSON file, exit with error if loading fails."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading file {filepath}: {e}", file=sys.stderr)
        sys.exit(1)


def calculate_event_metrics(
    cgm_data: Dict[str, Any],
    events_data: Dict[str, Any],
    metric_set_id: str,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Calculate metrics for all events in the events collection.

    Args:
        cgm_data: CGM time series data
        events_data: Events collection with events list
        metric_set_id: Unique identifier for this metric set
        verbose: Print progress information

    Returns:
        Derived metrics collection following the schema
    """
    calculator = CGMEventMetrics()

    all_metrics = []
    event_warnings = {}

    if verbose:
        print(f"Processing {len(events_data['events'])} events...", file=sys.stderr)

    for event in events_data['events']:
        if verbose:
            label = event.get('label', event['event_id'])
            print(f"  Event: {label}", file=sys.stderr)

        try:
            event_metrics = calculator.calculate_all_metrics(cgm_data, event)
            all_metrics.extend(event_metrics)

            if verbose:
                print(f"    ✓ Calculated {len(event_metrics)} metrics", file=sys.stderr)
                for metric in event_metrics:
                    print(
                        f"      - {metric['metric_name']}: {metric['value']:.1f} {metric['unit']}",
                        file=sys.stderr
                    )

                    coverage = metric.get('quality_summary', {}).get('coverage_percentage', 0)
                    if coverage < 70:
                        print(f"        ⚠ Low coverage: {coverage:.1f}%", file=sys.stderr)

        except Exception as e:
            event_warnings[event['event_id']] = str(e)
            if verbose:
                print(f"    ✗ Failed: {e}", file=sys.stderr)

    if verbose:
        print(f"\nTotal metrics calculated: {len(all_metrics)}", file=sys.stderr)

    metrics_collection = {
        "schema_version": "1.0.0",
        "metric_set_id": metric_set_id,
        "subject_id": events_data['subject_id'],
        "time_zone": events_data['time_zone'],
        "series_id": cgm_data['series_id'],
        "generated_at": datetime.now().isoformat(),
        "metrics": all_metrics
    }

    if event_warnings:
        metrics_collection['warnings'] = event_warnings

    return metrics_collection


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate windowed CGM metrics around events"
    )
    parser.add_argument(
        'cgm_file',
        help='Path to CGM time series JSON file'
    )
    parser.add_argument(
        'events_file',
        help='Path to meal/intervention events JSON file'
    )
    parser.add_argument(
        'output_file',
        help='Output path for derived metrics JSON'
    )
    parser.add_argument(
        '--metric-set-id',
        required=True,
        help='Unique identifier for this metric set (e.g., "experiment_1_meal_metrics")'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print progress information'
    )

    args = parser.parse_args()

    if args.verbose:
        print(f"Loading CGM data from {args.cgm_file}...", file=sys.stderr)
    cgm_data = load_json_file(args.cgm_file)

    if args.verbose:
        print(f"Loading events from {args.events_file}...", file=sys.stderr)
    events_data = load_json_file(args.events_file)

    if cgm_data['subject_id'] != events_data['subject_id']:
        print(
            f"Warning: Subject ID mismatch: CGM '{cgm_data['subject_id']}' vs Events '{events_data['subject_id']}'",
            file=sys.stderr
        )

    if args.verbose:
        print(f"\nCalculating metrics...", file=sys.stderr)

    try:
        metrics = calculate_event_metrics(
            cgm_data,
            events_data,
            args.metric_set_id,
            verbose=args.verbose
        )

        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        if args.verbose:
            print(f"\n✓ Metrics written to {args.output_file}", file=sys.stderr)

            coverage_warnings = sum(
                1 for m in metrics['metrics']
                if m.get('quality_summary', {}).get('coverage_percentage', 100) < 70
            )
            if coverage_warnings > 0:
                print(
                    f"⚠ {coverage_warnings} metrics have low coverage (<70%)",
                    file=sys.stderr
                )

    except Exception as e:
        print(f"Error calculating metrics: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
