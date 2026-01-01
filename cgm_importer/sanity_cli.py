#!/usr/bin/env python3
"""
Command-line interface for CGM signal sanity report generation.
"""

import argparse
import json
import sys
from pathlib import Path
from cgm_importer.sanity_report import CGMSanityReport


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate signal sanity report from CGM time series",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic report generation
  python -m cgm_importer.sanity_cli input.json

  # Save report to file with pretty printing
  python -m cgm_importer.sanity_cli input.json -o report.json --pretty
        """
    )

    parser.add_argument(
        "input",
        type=str,
        help="Path to the input CGM time series JSON file"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output JSON report file path (default: <input>.sanity.json)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print JSON output"
    )

    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip printing human-readable summary"
    )

    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Check input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".sanity.json")

    try:
        # Generate report
        print(f"Loading {input_path}...", file=sys.stderr)
        reporter = CGMSanityReport()

        schema_data = reporter.load_schema(str(input_path))
        print(f"  Found {len(schema_data.get('samples', []))} samples", file=sys.stderr)

        report = reporter.generate_report(schema_data)
        print(f"  Generated sanity report", file=sys.stderr)

        # Write output
        indent = 2 if args.pretty else None
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=indent, ensure_ascii=False)

        print(f"✓ Successfully wrote {output_path}", file=sys.stderr)

        # Print summary unless disabled
        if not args.no_summary:
            reporter.print_summary(report)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
