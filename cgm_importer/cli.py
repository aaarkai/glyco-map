#!/usr/bin/env python3
"""
Command-line interface for CGM XLSX importer.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from cgm_importer.importer import CGM_XLSX_Importer


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Convert CGM XLSX files to JSON schema format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with required parameters
  python -m cgm_importer.cli input.xlsx --subject-id user1 --device-id libre2-123 --timezone America/Los_Angeles

  # With custom output path and unit specification
  python -m cgm_importer.cli input.xlsx -o output.json -s user1 -d libre2-123 -z Asia/Shanghai -u mmol/L

  # Process with timezone from env variable
  CGM_TZ=Europe/London python -m cgm_importer.cli input.xlsx -s user1 -d libre2-123
        """
    )

    parser.add_argument(
        "input",
        type=str,
        help="Path to the input XLSX file"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output JSON file path (default: <input>.json)"
    )

    parser.add_argument(
        "-s", "--subject-id",
        type=str,
        required=True,
        help="Subject identifier (required)"
    )

    parser.add_argument(
        "-d", "--device-id",
        type=str,
        required=True,
        help="CGM device identifier (required)"
    )

    parser.add_argument(
        "-z", "--timezone",
        type=str,
        help="IANA timezone name (e.g., America/Los_Angeles). "
             "Can also be set via CGM_TZ environment variable."
    )

    parser.add_argument(
        "-u", "--unit",
        type=str,
        choices=["mg/dL", "mmol/L"],
        default="mg/dL",
        help="Glucose value unit (default: mg/dL)"
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate output against schema (if jsonschema is available)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty print JSON output (prettier than default)"
    )

    return parser


def validate_schema(data: dict, schema_path: str = "schemas/cgm-time-series.schema.json") -> None:
    """
    Validate data against the schema if jsonschema is available.

    Args:
        data: Schema data to validate
        schema_path: Path to schema file
    """
    try:
        import jsonschema
    except ImportError:
        print("Warning: jsonschema not available. Install with: pip install jsonschema", file=sys.stderr)
        return

    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)

        jsonschema.validate(data, schema)
        print("✓ Schema validation passed", file=sys.stderr)
    except jsonschema.exceptions.ValidationError as e:
        print(f"✗ Schema validation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Warning: Schema file not found at {schema_path}", file=sys.stderr)


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Check input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    # Determine timezone
    timezone = args.timezone or os.environ.get("CGM_TZ")
    if not timezone:
        print("Error: Timezone required. Use --timezone or set CGM_TZ environment variable", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".json")

    try:
        # Process the file
        print(f"Reading {input_path}...", file=sys.stderr)
        importer = CGM_XLSX_Importer()

        df = importer.read_xlsx(str(input_path))
        print(f"  Found {len(df)} CGM samples", file=sys.stderr)

        sampling_interval = importer.detect_sampling_interval(df["timestamp"])
        print(f"  Detected sampling interval: {sampling_interval:.1f} minutes", file=sys.stderr)

        # Detect artifacts
        quality_flags = importer.detect_artifacts(df["glucose_value"])
        flags_count = sum(1 for flags in quality_flags if flags)
        print(f"  Annotated {flags_count} samples with quality flags", file=sys.stderr)

        # Convert to schema
        schema_data = importer.convert_to_schema(
            df,
            subject_id=args.subject_id,
            device_id=args.device_id,
            timezone=timezone,
            unit=args.unit
        )

        # Validate if requested
        if args.validate:
            print("Validating schema...", file=sys.stderr)
            validate_schema(schema_data)

        # Write output
        indent = 2 if args.pretty else None
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f, indent=indent, ensure_ascii=False)

        print(f"✓ Successfully wrote {output_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
