#!/usr/bin/env python3
"""
Tests for meal and intervention event creation.
"""

import unittest
import tempfile
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from cgm_events.events import CGMEventCreator, CGMEventError


class TestCGMEvents(unittest.TestCase):
    """Test CGM event creation functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.creator = CGMEventCreator()
        self.test_subject_id = "test_subject_001"
        self.test_timezone = "America/Los_Angeles"
        self.base_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    def test_create_basic_event(self):
        """Test creating a basic meal event."""
        event = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time,
            label="Test lunch",
            estimated_carbs=45.0
        )

        self.assertEqual(event["event_type"], "meal")
        self.assertEqual(event["label"], "Test lunch")
        self.assertEqual(event["source"], "manual")
        self.assertEqual(event["annotation_quality"], 0.8)

        # Check carbs component
        self.assertIn("exposure_components", event)
        carbs = [c for c in event["exposure_components"] if c["name"] == "carbohydrate"][0]
        self.assertEqual(carbs["value"], 45.0)
        self.assertEqual(carbs["unit"], "g")

    def test_event_without_optional_fields(self):
        """Test creating event with minimal required fields."""
        event = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="snack",
            start_time=self.base_time
        )

        self.assertEqual(event["event_type"], "snack")
        self.assertNotIn("label", event)
        self.assertNotIn("end_time", event)
        self.assertNotIn("exposure_components", event)
        self.assertIn("event_id", event)

    def test_event_with_end_time(self):
        """Test creating event with end time and duration."""
        end_time = self.base_time + timedelta(minutes=30)
        event = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time,
            end_time=end_time
        )

        self.assertIn("end_time", event)
        self.assertIn("duration_minutes", event)
        self.assertEqual(event["duration_minutes"], 30.0)

    def test_event_context_tags(self):
        """Test adding context tags to notes."""
        event = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time,
            context_tags=["dinner", "restaurant", "post_exercise"],
            notes="Had pizza"
        )

        self.assertIn("notes", event)
        self.assertIn("dinner", event["notes"])
        self.assertIn("restaurant", event["notes"])
        self.assertIn("Context tags", event["notes"])

    def test_events_collection(self):
        """Test creating events collection."""
        events = [
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="breakfast",
                start_time=self.base_time
            ),
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="lunch",
                start_time=self.base_time + timedelta(hours=4)
            )
        ]

        collection = self.creator.create_events_collection(
            subject_id=self.test_subject_id,
            timezone=self.test_timezone,
            events=events,
            collection_notes="Test collection"
        )

        self.assertEqual(collection["schema_version"], "1.0.0")
        self.assertEqual(collection["subject_id"], self.test_subject_id)
        self.assertEqual(collection["time_zone"], self.test_timezone)
        self.assertEqual(len(collection["events"]), 2)
        self.assertEqual(collection["notes"], "Test collection")

    def test_validation_warnings(self):
        """Test event validation warnings."""
        # Event with low quality
        event_low_quality = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time,
            annotation_quality=0.3
        )
        warnings = self.creator.validate_event(event_low_quality)
        self.assertTrue(any("Low annotation quality" in w for w in warnings))

        # Event without carbs
        event_no_carbs = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time
        )
        warnings = self.creator.validate_event(event_no_carbs)
        self.assertTrue(any("No exposure components" in w for w in warnings))

        # Event without context
        event_no_context = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time
            # No context_tags and no notes
        )
        self.assertNotIn("notes", event_no_context)
        warnings = self.creator.validate_event(event_no_context)
        self.assertTrue(any("No context tags provided" in w for w in warnings))

    def test_error_cases(self):
        """Test error handling for invalid inputs."""
        # Missing subject_id
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id="",
                event_type="meal",
                start_time=self.base_time
            )

        # Missing event_type
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="",
                start_time=self.base_time
            )

        # No timezone
        naive_time = datetime(2024, 1, 1, 12, 0)
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=naive_time
            )

        # End time before start
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=self.base_time,
                end_time=self.base_time - timedelta(minutes=10)
            )

        # Invalid source
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=self.base_time,
                source="invalid"
            )

        # Invalid annotation quality
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=self.base_time,
                annotation_quality=1.5
            )

        # Invalid carbs
        with self.assertRaises(CGMEventError):
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=self.base_time,
                estimated_carbs=-10
            )

    def test_write_and_load_events(self):
        """Test writing events to file and loading them back."""
        events = [
            self.creator.create_event(
                subject_id=self.test_subject_id,
                event_type="meal",
                start_time=self.base_time,
                label="Test meal",
                estimated_carbs=50.0
            )
        ]

        collection = self.creator.create_events_collection(
            subject_id=self.test_subject_id,
            timezone=self.test_timezone,
            events=events
        )

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
            self.creator.write_events(collection, temp_file)

        try:
            # Load and verify
            with open(temp_file, 'r') as f:
                loaded = json.load(f)

            self.assertEqual(loaded["subject_id"], self.test_subject_id)
            self.assertEqual(loaded["time_zone"], self.test_timezone)
            self.assertEqual(len(loaded["events"]), 1)
            self.assertEqual(loaded["events"][0]["label"], "Test meal")

        finally:
            Path(temp_file).unlink()

    def test_unique_event_ids(self):
        """Test that each event gets a unique ID."""
        event1 = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time
        )

        event2 = self.creator.create_event(
            subject_id=self.test_subject_id,
            event_type="meal",
            start_time=self.base_time
        )

        self.assertNotEqual(event1["event_id"], event2["event_id"])


def run_tests():
    """Run the test suite."""
    unittest.main(verbosity=2)


if __name__ == "__main__":
    run_tests()
