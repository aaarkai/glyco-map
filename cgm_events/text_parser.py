"""
Event Text Parser

Parse simple timestamped event lines into CGM event annotations.
"""

from datetime import datetime
from typing import Dict, List, Any, Iterable, Optional
from zoneinfo import ZoneInfo

from cgm_events.events import CGMEventCreator, CGMEventError


class CGMEventTextParser:
    """
    Parse lines in the format:
      YYYY-MM-DD HH:MM <label>
    """

    def __init__(self):
        self.creator = CGMEventCreator()

    def parse_lines(
        self,
        lines: Iterable[str],
        subject_id: str,
        timezone: str,
        event_type: str = "meal",
        source: str = "manual",
        annotation_quality: float = 0.8,
        merge_same_time: bool = True,
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        tzinfo = ZoneInfo(timezone)
        grouped: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []

        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                raise ValueError(
                    f"Invalid line {idx}: expected 'YYYY-MM-DD HH:MM <label>'"
                )

            date_str, time_str, label = parts
            try:
                naive_time = datetime.strptime(
                    f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                )
            except ValueError as exc:
                raise ValueError(f"Invalid timestamp at line {idx}: {exc}") from exc

            start_time = naive_time.replace(tzinfo=tzinfo)
            start_key = start_time.isoformat()

            if merge_same_time:
                if start_key not in grouped:
                    grouped[start_key] = {
                        "start_time": start_time,
                        "labels": [],
                    }
                    order.append(start_key)
                grouped[start_key]["labels"].append(label.strip())
                continue

            try:
                event = self.creator.create_event(
                    subject_id=subject_id,
                    event_type=event_type,
                    start_time=start_time,
                    label=label.strip(),
                    source=source,
                    annotation_quality=annotation_quality,
                )
            except CGMEventError as exc:
                raise ValueError(f"Failed to create event at line {idx}: {exc}") from exc

            events.append(event)

        if merge_same_time:
            for key in order:
                payload = grouped[key]
                combined_label = " / ".join(payload["labels"])
                try:
                    event = self.creator.create_event(
                        subject_id=subject_id,
                        event_type=event_type,
                        start_time=payload["start_time"],
                        label=combined_label,
                        source=source,
                        annotation_quality=annotation_quality,
                    )
                except CGMEventError as exc:
                    raise ValueError(f"Failed to create event at {key}: {exc}") from exc
                events.append(event)

        return events

    def parse_file(
        self,
        filepath: str,
        subject_id: str,
        timezone: str,
        event_type: str = "meal",
        source: str = "manual",
        annotation_quality: float = 0.8,
        encoding: str = "utf-8",
        merge_same_time: bool = True,
    ) -> List[Dict[str, Any]]:
        with open(filepath, "r", encoding=encoding) as handle:
            lines = handle.readlines()
        return self.parse_lines(
            lines,
            subject_id=subject_id,
            timezone=timezone,
            event_type=event_type,
            source=source,
            annotation_quality=annotation_quality,
            merge_same_time=merge_same_time,
        )
