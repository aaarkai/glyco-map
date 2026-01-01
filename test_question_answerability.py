#!/usr/bin/env python3
"""
Tests for question answerability evaluation.
"""

import unittest
from datetime import datetime, timezone, timedelta

from cgm_questions.answerability import QuestionAnswerabilityEvaluator


class TestQuestionAnswerability(unittest.TestCase):
    """Test answerability logic for causal questions."""

    def setUp(self):
        self.evaluator = QuestionAnswerabilityEvaluator(min_events_per_group=2)
        self.base_time = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)

    def _make_event(self, event_id, label, offset_minutes):
        start_time = self.base_time + timedelta(minutes=offset_minutes)
        return {
            "event_id": event_id,
            "event_type": "meal",
            "start_time": start_time.isoformat(),
            "label": label,
            "source": "manual",
            "annotation_quality": 0.9,
        }

    def _make_metric(self, event_id, metric_name, coverage=0.9):
        return {
            "event_id": event_id,
            "metric_name": metric_name,
            "value": 10.0,
            "unit": "mg/dL*min",
            "coverage_ratio": coverage,
            "window": {
                "relative_to": "event_start",
                "start_offset_minutes": 0,
                "end_offset_minutes": 120
            }
        }

    def _base_question(self):
        return {
            "schema_version": "1.0.0",
            "question_id": "q1",
            "subject_id": "test_subject",
            "time_zone": "UTC",
            "type": "causal_comparison",
            "exposure": {
                "event_type": "meal",
                "selector": {
                    "component": "label",
                    "operator": "=",
                    "value": "food_x",
                    "unit": "text"
                }
            },
            "comparison": {
                "event_type": "meal",
                "selector": {
                    "component": "label",
                    "operator": "=",
                    "value": "food_y",
                    "unit": "text"
                }
            },
            "outcome": {
                "metric_name": "iAUC",
                "window": {
                    "relative_to": "event_start",
                    "start_offset_minutes": 0,
                    "end_offset_minutes": 120
                },
                "unit": "mg/dL*min"
            },
            "condition": [],
            "time_span": {
                "start_time": "2024-01-01T00:00:00+00:00",
                "end_time": "2024-12-31T23:59:59+00:00"
            },
            "assumptions": ["no overlapping events within 30 minutes"]
        }

    def test_answerable_with_sufficient_events(self):
        events_data = {
            "subject_id": "test_subject",
            "events": [
                self._make_event("evt_x1", "food_x", 0),
                self._make_event("evt_x2", "food_x", 200),
                self._make_event("evt_y1", "food_y", 400),
                self._make_event("evt_y2", "food_y", 600),
            ]
        }
        metrics_data = {
            "subject_id": "test_subject",
            "metrics": [
                self._make_metric("evt_x1", "iAUC"),
                self._make_metric("evt_x2", "iAUC"),
                self._make_metric("evt_y1", "iAUC"),
                self._make_metric("evt_y2", "iAUC"),
            ]
        }

        result = self.evaluator.evaluate(self._base_question(), events_data, metrics_data)

        self.assertTrue(result["answerable"])
        self.assertEqual(result["reasons"], [])

    def test_insufficient_repeats(self):
        events_data = {
            "subject_id": "test_subject",
            "events": [
                self._make_event("evt_x1", "food_x", 0),
                self._make_event("evt_y1", "food_y", 200),
            ]
        }
        metrics_data = {
            "subject_id": "test_subject",
            "metrics": [
                self._make_metric("evt_x1", "iAUC"),
                self._make_metric("evt_y1", "iAUC"),
            ]
        }

        result = self.evaluator.evaluate(self._base_question(), events_data, metrics_data)

        self.assertFalse(result["answerable"])
        codes = [r["code"] for r in result["reasons"]]
        self.assertIn("insufficient_repeats_exposure", codes)
        self.assertIn("insufficient_repeats_comparison", codes)

    def test_missing_metrics(self):
        events_data = {
            "subject_id": "test_subject",
            "events": [
                self._make_event("evt_x1", "food_x", 0),
                self._make_event("evt_x2", "food_x", 200),
                self._make_event("evt_y1", "food_y", 400),
                self._make_event("evt_y2", "food_y", 600),
            ]
        }
        metrics_data = {
            "subject_id": "test_subject",
            "metrics": [
                self._make_metric("evt_x1", "iAUC"),
                self._make_metric("evt_y1", "iAUC"),
                self._make_metric("evt_y2", "iAUC"),
            ]
        }

        result = self.evaluator.evaluate(self._base_question(), events_data, metrics_data)

        self.assertFalse(result["answerable"])
        codes = [r["code"] for r in result["reasons"]]
        self.assertIn("missing_metric", codes)

    def test_confounded_events_reduce_usable(self):
        events_data = {
            "subject_id": "test_subject",
            "events": [
                self._make_event("evt_x1", "food_x", 0),
                self._make_event("evt_x2", "food_x", 10),
                self._make_event("evt_y1", "food_y", 300),
                self._make_event("evt_y2", "food_y", 600),
            ]
        }
        metrics_data = {
            "subject_id": "test_subject",
            "metrics": [
                self._make_metric("evt_x1", "iAUC"),
                self._make_metric("evt_x2", "iAUC"),
                self._make_metric("evt_y1", "iAUC"),
                self._make_metric("evt_y2", "iAUC"),
            ]
        }

        result = self.evaluator.evaluate(self._base_question(), events_data, metrics_data)

        self.assertFalse(result["answerable"])
        codes = [r["code"] for r in result["reasons"]]
        self.assertIn("insufficient_repeats_exposure", codes)

    def test_time_of_day_in_condition(self):
        question = self._base_question()
        question["condition"] = [{
            "name": "time_of_day",
            "operator": "in",
            "value": ["08:00", "09:00"],
            "unit": "local_time"
        }]

        events_data = {
            "subject_id": "test_subject",
            "events": [
                self._make_event("evt_x1", "food_x", 0),
                self._make_event("evt_x2", "food_x", 60),
                self._make_event("evt_y1", "food_y", 120),
                self._make_event("evt_y2", "food_y", 180),
            ]
        }
        metrics_data = {
            "subject_id": "test_subject",
            "metrics": [
                self._make_metric("evt_x1", "iAUC"),
                self._make_metric("evt_x2", "iAUC"),
                self._make_metric("evt_y1", "iAUC"),
                self._make_metric("evt_y2", "iAUC"),
            ]
        }

        result = self.evaluator.evaluate(question, events_data, metrics_data)
        self.assertTrue(result["answerable"])

    def test_unsupported_metric_delta_peak(self):
        question = self._base_question()
        question["outcome"]["metric_name"] = "delta_peak"

        result = self.evaluator.evaluate(question, {"events": []}, {"metrics": []})
        self.assertFalse(result["answerable"])
        codes = [r["code"] for r in result["reasons"]]
        self.assertIn("unsupported_metric", codes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
