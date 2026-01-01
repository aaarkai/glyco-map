"""
Meal and Intervention Events Management

Tools for creating and managing event annotations.
IMPORTANT: Events are CLAIMS about exposures, not ground truth measurements.
"""

import json
import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional


class CGMEventError(Exception):
    """Base exception for CGM event operations."""
    pass


class CGMEventCreator:
    """
    Create meal and intervention event annotations.

    IMPORTANT DESIGN PRINCIPLE:
    Events are CLAIMS made by the subject or observer about exposures.
    They are NOT ground truth measurements. Annotation quality may vary.
    """

    # Valid context tags for events
    CONTEXT_TAGS = {
        "time_of_day": ["breakfast", "lunch", "dinner", "snack", "late_night"],
        "activity_context": ["post_exercise", "pre_exercise", "sedentary", "active"],
        "meal_context": ["home_cooked", "restaurant", "takeout", "packaged"],
        "special_contexts": ["illness", "stress", "travel", "celebration"]
    }

    def __init__(self):
        pass

    def create_event(
        self,
        subject_id: str,
        event_type: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        label: Optional[str] = None,
        estimated_carbs: Optional[float] = None,
        context_tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        source: str = "manual",
        annotation_quality: float = 0.8
    ) -> Dict[str, Any]:
        """
        Create a single event annotation.

        IMPORTANT: This creates a CLAIM about an exposure, not a measurement.
        The quality and accuracy depend on the source and annotation method.

        Args:
            subject_id: Unique identifier for the subject
            event_type: Type of event (e.g., "meal", "snack", "exercise")
            start_time: When the event started (with timezone)
            end_time: When the event ended (optional)
            label: Free-text description (e.g., "pizza dinner")
            estimated_carbs: Estimated carbohydrate content in grams (optional)
            context_tags: Context tags for analysis (e.g., ["dinner", "restaurant"])
            notes: Additional free-text notes
            source: Source of annotation (manual/app/import/api/other)
            annotation_quality: Subjective quality score 0-1 (default 0.8)

        Returns:
            Event dictionary conforming to meal-intervention-events schema

        Raises:
            CGMEventError: If validation fails
        """
        # Validate inputs
        if not subject_id or not subject_id.strip():
            raise CGMEventError("subject_id is required")

        if not event_type or not event_type.strip():
            raise CGMEventError("event_type is required")

        if start_time.tzinfo is None:
            raise CGMEventError("start_time must have timezone information")

        if end_time and end_time.tzinfo is None:
            raise CGMEventError("end_time must have timezone information")

        if end_time and end_time <= start_time:
            raise CGMEventError("end_time must be after start_time")

        if annotation_quality < 0 or annotation_quality > 1:
            raise CGMEventError("annotation_quality must be between 0 and 1")

        if source not in ["manual", "app", "import", "api", "other"]:
            raise CGMEventError("source must be one of: manual, app, import, api, other")

        # Create exposure components
        exposure_components = []

        if estimated_carbs is not None:
            if estimated_carbs < 0:
                raise CGMEventError("estimated_carbs cannot be negative")
            exposure_components.append({
                "name": "carbohydrate",
                "value": float(estimated_carbs),
                "unit": "g"
            })

        # Generate event ID
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        # Create event
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "start_time": start_time.isoformat(),
            "source": source
        }

        if end_time:
            event["end_time"] = end_time.isoformat()
            duration_minutes = (end_time - start_time).total_seconds() / 60
            event["duration_minutes"] = round(duration_minutes, 2)

        if exposure_components:
            event["exposure_components"] = exposure_components

        event["annotation_quality"] = round(annotation_quality, 2)

        if label and label.strip():
            event["label"] = label.strip()

        if notes and notes.strip():
            event["notes"] = notes.strip()

        # Add context tags as structured notes
        if context_tags:
            valid_contexts = []
            for tag in context_tags:
                tag_lower = tag.lower().replace(" ", "_")
                valid_contexts.append(tag_lower)

            if valid_contexts:
                context_str = f"Context tags: {', '.join(valid_contexts)}"
                if "notes" in event:
                    event["notes"] = f"{event['notes']}\n{context_str}"
                else:
                    event["notes"] = context_str
        else:
            context_str = None

        return event

    def create_events_collection(
        self,
        subject_id: str,
        timezone: str,
        events: List[Dict[str, Any]],
        collection_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a complete events collection document.

        Args:
            subject_id: Unique identifier for the subject
            timezone: IANA timezone name
            events: List of event dictionaries
            collection_notes: Notes about the collection as a whole

        Returns:
            Events collection conforming to meal-intervention-events schema
        """
        if not events:
            raise CGMEventError("At least one event is required")

        # Generate collection ID based on content
        event_ids_str = ",".join(sorted([e["event_id"] for e in events]))
        collection_hash = hashlib.sha256(
            f"{subject_id}_{timezone}_{event_ids_str}".encode()
        ).hexdigest()[:16]
        events_id = f"evts_{collection_hash}"

        collection = {
            "schema_version": "1.0.0",
            "events_id": events_id,
            "subject_id": subject_id,
            "time_zone": timezone,
            "events": events
        }

        if collection_notes:
            collection["notes"] = collection_notes

        return collection

    def write_events(self, events_data: Dict[str, Any], filepath: str) -> None:
        """
        Write events collection to JSON file.

        Args:
            events_data: Events collection dictionary
            filepath: Output file path
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=2, ensure_ascii=False)

    def validate_event(self, event: Dict[str, Any]) -> List[str]:
        """
        Validate an event and return list of warnings.

        Warnings indicate potential issues but don't prevent creation.
        These help users understand limitations of their annotations.

        Args:
            event: Event dictionary to validate

        Returns:
            List of warning strings
        """
        warnings = []

        # Warn about low annotation quality
        if event.get("annotation_quality", 1.0) < 0.5:
            warnings.append(
                "Low annotation quality (<0.5). This event may be unreliable for analysis."
            )

        # Warn about missing exposure components
        if not event.get("exposure_components"):
            warnings.append(
                "No exposure components (e.g., carbs) provided. "
                "Analysis may be limited without dose information."
            )

        # Warn about short duration
        if event.get("duration_minutes", 0) < 5:
            warnings.append(
                "Very short event (<5 min). May not represent a complete exposure."
            )

        # Warn about manual entry (lowest quality source)
        if event.get("source") == "manual":
            warnings.append(
                "Manual entry source. Consider validating with app/import data when possible."
            )

        # Warn about missing context
        notes = event.get("notes", "")
        if not notes or "context" not in notes.lower():
            warnings.append(
                "No context tags provided. Context (time, setting, activity) improves analysis."
            )

        return warnings

    def print_event_summary(self, event: Dict[str, Any]) -> None:
        """
        Print a human-readable summary of an event.

        Args:
            event: Event dictionary
        """
        import sys

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"EVENT CLAIM (not ground truth measurement)", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

        print(f"Event ID: {event['event_id']}", file=sys.stderr)
        print(f"Type: {event['event_type']}", file=sys.stderr)

        if 'label' in event:
            print(f"Label: {event['label']}", file=sys.stderr)

        print(f"Start: {event['start_time']}", file=sys.stderr)

        if 'end_time' in event:
            print(f"End: {event['end_time']}", file=sys.stderr)
            print(f"Duration: {event.get('duration_minutes', 'N/A')} minutes", file=sys.stderr)

        if 'exposure_components' in event:
            print(f"\nExposure Components:", file=sys.stderr)
            for comp in event['exposure_components']:
                print(f"  - {comp['name']}: {comp['value']} {comp['unit']}", file=sys.stderr)

        print(f"\nSource: {event['source']}", file=sys.stderr)
        print(f"Annotation Quality: {event['annotation_quality']}/1.0", file=sys.stderr)

        if 'notes' in event:
            print(f"\nNotes:\n  {event['notes']}\n", file=sys.stderr)

        warnings = self.validate_event(event)
        if warnings:
            print(f"{'='*60}", file=sys.stderr)
            print(f"VALIDATION WARNINGS:", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            for warning in warnings:
                print(f"⚠ {warning}", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
