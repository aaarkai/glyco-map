#!/usr/bin/env python3
"""
Command-line interface for creating meal and intervention events.

IMPORTANT: Events created with this tool are CLAIMS about exposures,
not ground truth measurements. Always consider annotation quality.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from cgm_events.events import CGMEventCreator, CGMEventError


def parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string with timezone."""
    try:
        # Try with timezone info
        return datetime.fromisoformat(dt_str)
    except ValueError:
        raise CGMEventError(
            f"Invalid datetime format: {dt_str}. "
            "Use ISO 8601 format with timezone (e.g., 2024-01-01T12:00:00-08:00)"
        )


def parse_context_tags(tags_str: str) -> list:
    """Parse comma-separated context tags."""
    if not tags_str or not tags_str.strip():
        return []
    return [tag.strip() for tag in tags_str.split(',') if tag.strip()]


def create_interactive_event(creator: CGMEventCreator, timezone: str) -> dict:
    """Create an event interactively via prompts."""
    print("\n" + "="*60)
    print("CREATE EVENT CLAIM (not ground truth measurement)")
    print("="*60 + "\n")

    print("⚠ IMPORTANT: Events are CLAIMS about exposures, not measurements.")
    print("  Annotation quality affects analysis reliability.\n")

    # Required fields
    subject_id = input("Subject ID: ").strip()
    if not subject_id:
        raise CGMEventError("Subject ID is required")

    event_type = input("Event type (meal/snack/exercise/other): ").strip().lower()
    if not event_type:
        event_type = "meal"

    label = input("Label/description (e.g., 'pizza dinner'): ").strip()

    start_time_str = input(f"Start time (ISO format, {timezone}): ").strip()
    if not start_time_str:
        raise CGMEventError("Start time is required")
    start_time = parse_datetime(start_time_str)

    # Optional: end time
    end_time = None
    end_time_str = input("End time (optional, press Enter to skip): ").strip()
    if end_time_str:
        end_time = parse_datetime(end_time_str)

    # Optional: carbs
    estimated_carbs = None
    carbs_str = input("Estimated carbs in grams (optional): ").strip()
    if carbs_str:
        try:
            estimated_carbs = float(carbs_str)
        except ValueError:
            raise CGMEventError("Carbs must be a number")

    # Context tags
    print("\nContext tags (help with analysis):")
    print("  Time: breakfast, lunch, dinner, snack, late_night")
    print("  Activity: post_exercise, pre_exercise, sedentary, active")
    print("  Setting: home_cooked, restaurant, takeout, packaged")
    print("  Special: illness, stress, travel, celebration")

    tags_str = input("Context tags (comma-separated): ").strip()
    context_tags = parse_context_tags(tags_str)

    # Optional: notes
    notes = input("Additional notes: ").strip()

    # Source and quality
    source = input("Source (manual/app/import/api) [manual]: ").strip().lower()
    if not source:
        source = "manual"

    quality_str = input("Annotation quality 0-1 [0.8]: ").strip()
    annotation_quality = 0.8
    if quality_str:
        try:
            annotation_quality = float(quality_str)
        except ValueError:
            raise CGMEventError("Quality must be a number between 0 and 1")

    # Create the event
    event = creator.create_event(
        subject_id=subject_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        label=label,
        estimated_carbs=estimated_carbs,
        context_tags=context_tags,
        notes=notes,
        source=source,
        annotation_quality=annotation_quality
    )

    return event


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="Create meal and intervention event annotations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create event interactively
  python -m cgm_events.cli events.json -s subject1 -z America/Los_Angeles

  # Create event with all parameters
  python -m cgm_events.cli events.json -s subject1 -z America/Los_Angeles \\
    -t meal -l "pizza dinner" -c "5:30 PM" -e "6:15 PM" \\
    --carbs 75 --tags dinner,restaurant --notes "ate 3 slices"

  # Create multiple events interactively
  python -m cgm_events.cli events.json -s subject1 -z America/Los_Angeles --multiple

IMPORTANT: Events are CLAIMS about exposures, not ground truth measurements.
        """
    )

    parser.add_argument(
        "output",
        type=str,
        help="Output JSON file for events collection"
    )

    parser.add_argument(
        "-s", "--subject-id",
        type=str,
        required=True,
        help="Subject identifier"
    )

    parser.add_argument(
        "-z", "--timezone",
        type=str,
        required=True,
        help="IANA timezone name (e.g., America/Los_Angeles)"
    )

    parser.add_argument(
        "-t", "--event-type",
        type=str,
        default="meal",
        choices=["meal", "snack", "exercise", "medication", "fasting", "other"],
        help="Event type"
    )

    parser.add_argument(
        "-l", "--label",
        type=str,
        help="Free-text label/description"
    )

    parser.add_argument(
        "-c", "--start-time",
        type=str,
        help="Start time (ISO format with timezone)"
    )

    parser.add_argument(
        "-e", "--end-time",
        type=str,
        help="End time (ISO format with timezone)"
    )

    parser.add_argument(
        "--carbs",
        type=float,
        help="Estimated carbohydrates in grams"
    )

    parser.add_argument(
        "--tags",
        type=str,
        help="Context tags (comma-separated)"
    )

    parser.add_argument(
        "--notes",
        type=str,
        help="Additional notes"
    )

    parser.add_argument(
        "--source",
        type=str,
        default="manual",
        choices=["manual", "app", "import", "api"],
        help="Annotation source"
    )

    parser.add_argument(
        "--quality",
        type=float,
        default=0.8,
        help="Annotation quality 0-1 (default: 0.8)"
    )

    parser.add_argument(
        "--multiple",
        action="store_true",
        help="Create multiple events interactively"
    )

    parser.add_argument(
        "--collection-notes",
        type=str,
        help="Notes about the event collection"
    )

    return parser


def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    creator = CGMEventCreator()
    events = []

    try:
        # Check if file exists to load existing events
        output_path = Path(args.output)
        if output_path.exists():
            print(f"Loading existing events from {output_path}...")
            with open(output_path, 'r') as f:
                existing_data = json.load(f)
                if existing_data.get('subject_id') != args.subject_id:
                    raise CGMEventError(
                        f"Subject ID mismatch: {existing_data.get('subject_id')} vs {args.subject_id}"
                    )
                if existing_data.get('time_zone') != args.timezone:
                    raise CGMEventError(
                        f"Timezone mismatch: {existing_data.get('time_zone')} vs {args.timezone}"
                    )
                events = existing_data.get('events', [])
                print(f"  Found {len(events)} existing events")

        # Create events
        if args.multiple or (not args.start_time and not args.label):
            # Interactive mode - multiple events
            while True:
                try:
                    event = create_interactive_event(creator, args.timezone)
                    events.append(event)

                    creator.print_event_summary(event)

                    # Check if user wants to add more
                    cont = input("\nAdd another event? (y/n): ").strip().lower()
                    if cont != 'y':
                        break
                except CGMEventError as e:
                    print(f"\nError: {e}", file=sys.stderr)
                    print("Please try again.\n")
                    continue
        else:
            # Command-line mode - single event
            if not args.start_time:
                raise CGMEventError("--start-time is required in non-interactive mode")

            # Parse times
            start_time = parse_datetime(args.start_time)
            end_time = parse_datetime(args.end_time) if args.end_time else None

            # Parse context tags
            context_tags = parse_context_tags(args.tags)

            # Create event
            event = creator.create_event(
                subject_id=args.subject_id,
                event_type=args.event_type,
                start_time=start_time,
                end_time=end_time,
                label=args.label,
                estimated_carbs=args.carbs,
                context_tags=context_tags,
                notes=args.notes,
                source=args.source,
                annotation_quality=args.quality
            )

            events.append(event)
            creator.print_event_summary(event)

        # Create events collection
        if events:
            events_data = creator.create_events_collection(
                subject_id=args.subject_id,
                timezone=args.timezone,
                events=events,
                collection_notes=args.collection_notes
            )

            # Write to file
            creator.write_events(events_data, str(output_path))

            print(f"\n✓ Successfully wrote {len(events)} events to {output_path}",
                  file=sys.stderr)

        else:
            print("\nNo events created.", file=sys.stderr)

    except CGMEventError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
