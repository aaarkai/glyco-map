#!/usr/bin/env python3
"""
Command-line interface for evaluating event quality against CGM data.

Evaluates whether events support reliable causal analysis by checking:
1. Overlap with CGM coverage
2. Isolation from other events
3. Sufficient pre-event baseline
"""

import argparse
import json
import sys
from pathlib import Path

from cgm_events.event_quality import EventQualityEvaluator


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate event quality for causal analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Evaluate events against CGM data
  python -m cgm_events.quality_cli events.json cgm_data.json

  # Save evaluation results
  python -m cgm_events.quality_cli events.json cgm_data.json -o quality_report.json

  # Show summary only (no detailed output)
  python -m cgm_events.quality_cli events.json cgm_data.json --summary-only
        """
    )

    parser.add_argument(
        "events_file",
        type=str,
        help="Path to events JSON file"
    )

    parser.add_argument(
        "cgm_file",
        type=str,
        help="Path to CGM data JSON file"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file for quality evaluation JSON"
    )

    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Show only summary, not per-event details"
    )

    parser.add_argument(
        "--min-baseline",
        type=int,
        default=60,
        help="Minimum baseline minutes (default: 60)"
    )

    parser.add_argument(
        "--min-isolation",
        type=int,
        default=30,
        help="Minimum isolation minutes (default: 30)"
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        help="Minimum coverage fraction (default: 0.8)"
    )

    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Check files exist
    events_path = Path(args.events_file)
    cgm_path = Path(args.cgm_file)

    if not events_path.exists():
        print(f"Error: Events file '{events_path}' not found", file=sys.stderr)
        sys.exit(1)

    if not cgm_path.exists():
        print(f"Error: CGM file '{cgm_path}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        # Load and evaluate
        print(f"Loading events from {events_path}...", file=sys.stderr)
        print(f"Loading CGM data from {cgm_path}...", file=sys.stderr)

        evaluator = EventQualityEvaluator()

        # Configure thresholds
        evaluator.min_baseline_minutes = args.min_baseline
        evaluator.min_isolation_minutes = args.min_isolation
        evaluator.min_during_coverage = args.min_coverage

        events_data = evaluator.load_events(str(events_path))

        print(f"\nEvaluating {len(events_data.get('events', []))} events...",
              file=sys.stderr)

        evaluation = evaluator.evaluate_all_events(events_data, str(cgm_path))

        # Print summary
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"EVENT QUALITY EVALUATION SUMMARY", file=sys.stderr)
        print(f"{'='*70}\n", file=sys.stderr)

        print(f"Events: {evaluation['total_events']}", file=sys.stderr)
        print(f"Usable for analysis: {evaluation['usable_events']}", file=sys.stderr)
        print(f"Usability rate: {evaluation['usability_fraction']:.1%}", file=sys.stderr)

        # Show quality distribution
        quality_scores = [e['quality_score'] for e in evaluation['evaluations']]
        if quality_scores:
            print(f"\nQuality Score Distribution:", file=sys.stderr)
            print(f"  High (>=0.8): {sum(1 for q in quality_scores if q >= 0.8)}", file=sys.stderr)
            print(f"  Medium (0.6-0.8): {sum(1 for q in quality_scores if 0.6 <= q < 0.8)}", file=sys.stderr)
            print(f"  Low (<0.6): {sum(1 for q in quality_scores if q < 0.6)}", file=sys.stderr)

        print(f"\n{'='*70}\n", file=sys.stderr)

        # Print per-event details unless summary-only
        if not args.summary_only:
            for eval_result in evaluation['evaluations']:
                evaluator.print_evaluation_summary(eval_result)

        # Write output if requested
        if args.output:
            output_path = Path(args.output)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(evaluation, f, indent=2, ensure_ascii=False)
            print(f"✓ Wrote evaluation to {output_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
