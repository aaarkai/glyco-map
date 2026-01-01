#!/usr/bin/env python3
"""
Command-line interface for parsing event text files.
"""

import argparse
import json
import sys
from pathlib import Path

from cgm_events.text_parser import CGMEventTextParser
from cgm_events.events import CGMEventCreator


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a text file of timestamped events into events JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Format:
  YYYY-MM-DD HH:MM <label>

Example:
  2026-01-01 12:00 hotdog
  2026-01-01 13:30 milk tea
  2026-01-01 19:00 dinner
        """,
    )

    parser.add_argument("input", type=str, help="Path to input text file")
    parser.add_argument("output", type=str, help="Path to output events JSON file")

    parser.add_argument("--subject-id", required=True, help="Subject identifier")
    parser.add_argument("--timezone", required=True, help="IANA timezone name")
    parser.add_argument("--event-type", default="meal", help="Event type (default: meal)")
    parser.add_argument("--source", default="manual", help="Event source (default: manual)")
    parser.add_argument(
        "--annotation-quality",
        type=float,
        default=0.8,
        help="Annotation quality score 0-1 (default: 0.8)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    parser_engine = CGMEventTextParser()
    creator = CGMEventCreator()

    try:
        events = parser_engine.parse_file(
            str(input_path),
            subject_id=args.subject_id,
            timezone=args.timezone,
            event_type=args.event_type,
            source=args.source,
            annotation_quality=args.annotation_quality,
        )

        events_data = creator.create_events_collection(
            subject_id=args.subject_id,
            timezone=args.timezone,
            events=events,
            collection_notes=f"Parsed from {input_path.name}",
        )

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(events_data, handle, indent=2 if args.pretty else None, ensure_ascii=False)

        print(f"✓ Wrote events to {output_path}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
