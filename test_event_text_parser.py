#!/usr/bin/env python3
"""
Tests for event text parsing.
"""

import unittest
from cgm_events.text_parser import CGMEventTextParser


class TestEventTextParser(unittest.TestCase):
    def setUp(self):
        self.parser = CGMEventTextParser()

    def test_parse_lines_basic(self):
        lines = [
            "2026-01-01 12:00 hotdog\n",
            "2026-01-01 13:30 milk tea\n",
            "2026-01-01 19:00 dinner\n",
        ]

        events = self.parser.parse_lines(
            lines,
            subject_id="subject_001",
            timezone="Asia/Shanghai",
        )

        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["label"], "hotdog")
        self.assertTrue(events[0]["start_time"].endswith("+08:00"))

    def test_parse_lines_invalid(self):
        lines = ["2026-01-01 badline\n"]
        with self.assertRaises(ValueError):
            self.parser.parse_lines(
                lines,
                subject_id="subject_001",
                timezone="Asia/Shanghai",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
