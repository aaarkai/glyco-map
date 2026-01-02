"""
Question answerability evaluation.

Determines whether a causal question is answerable given events and metrics.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple


class QuestionAnswerabilityEvaluator:
    """
    Evaluate whether a causal question is answerable with current data.
    """

    def __init__(
        self,
        min_events_per_group: int = 2,
        min_metric_coverage: float = 0.7,
        min_isolation_minutes: int = 30,
        default_event_duration_minutes: int = 30,
    ):
        self.min_events_per_group = min_events_per_group
        self.min_metric_coverage = min_metric_coverage
        self.min_isolation_minutes = min_isolation_minutes
        self.default_event_duration_minutes = default_event_duration_minutes

    def evaluate(
        self,
        question: Dict[str, Any],
        events_data: Dict[str, Any],
        metrics_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate answerability for a question using events and derived metrics.
        """
        reasons: List[Dict[str, Any]] = []
        data_requirements: List[Dict[str, Any]] = []

        events = self._extract_events(events_data)
        metrics = self._extract_metrics(metrics_data)
        metrics_index = self._index_metrics(metrics)

        subject_id = question.get("subject_id")
        time_zone = question.get("time_zone")
        question_id = question.get("question_id", "unknown")

        metric_name = question["outcome"]["metric_name"]
        summary = {
            "question_id": question_id,
            "subject_id": subject_id,
            "metric_name": metric_name,
            "metric_window": question["outcome"].get("window"),
            "time_span": question.get("time_span"),
            "min_events_per_group": self.min_events_per_group,
            "min_metric_coverage": self.min_metric_coverage,
            "min_isolation_minutes": self.min_isolation_minutes,
        }

        if events_data.get("subject_id") and subject_id and events_data.get("subject_id") != subject_id:
            reasons.append(self._reason(
                "subject_id_mismatch",
                f"Events subject_id {events_data.get('subject_id')} does not match question subject_id {subject_id}.",
                blocking=True,
            ))

        if metrics_data.get("subject_id") and subject_id and metrics_data.get("subject_id") != subject_id:
            reasons.append(self._reason(
                "subject_id_mismatch",
                f"Metrics subject_id {metrics_data.get('subject_id')} does not match question subject_id {subject_id}.",
                blocking=True,
            ))

        time_span_start, time_span_end = self._parse_time_span(question.get("time_span"))
        events_in_span = [
            event for event in events
            if self._event_in_span(event, time_span_start, time_span_end)
        ]

        exposure_def = question["exposure"]
        comparison_def = question["comparison"]
        conditions = question.get("condition", [])

        exposure_matches = [
            event for event in events_in_span
            if self._matches_event_definition(event, exposure_def)
            and self._matches_conditions(event, conditions, time_zone)
        ]
        comparison_matches = [
            event for event in events_in_span
            if self._matches_event_definition(event, comparison_def)
            and self._matches_conditions(event, conditions, time_zone)
        ]

        exposure_ids = [event["event_id"] for event in exposure_matches]
        comparison_ids = [event["event_id"] for event in comparison_matches]
        overlap_ids = sorted(set(exposure_ids) & set(comparison_ids))

        if overlap_ids:
            reasons.append(self._reason(
                "ambiguous_event_definition",
                "Exposure and comparison selectors match the same events.",
                blocking=True,
                affected_event_ids=overlap_ids,
            ))

        confounded_ids = self._find_confounded_events(
            events_in_span,
            self.min_isolation_minutes,
        )

        exposure_stats = self._evaluate_group(
            exposure_matches,
            metrics_index,
            question,
            confounded_ids,
        )
        comparison_stats = self._evaluate_group(
            comparison_matches,
            metrics_index,
            question,
            confounded_ids,
        )

        reasons.extend(self._group_reasons("exposure", exposure_stats))
        reasons.extend(self._group_reasons("comparison", comparison_stats))

        data_requirements.extend(self._group_data_requirements("exposure", exposure_stats, exposure_def))
        data_requirements.extend(self._group_data_requirements("comparison", comparison_stats, comparison_def))

        if overlap_ids:
            data_requirements.append({
                "type": "refine_definitions",
                "detail": "Refine exposure/comparison selectors to avoid overlapping events.",
                "event_ids": overlap_ids,
            })

        answerable = not any(reason["blocking"] for reason in reasons)

        return {
            "evaluation_version": "1.0.0",
            "question_id": question_id,
            "subject_id": subject_id,
            "answerable": answerable,
            "summary": summary,
            "reasons": reasons,
            "data_requirements": data_requirements,
            "match_stats": {
                "exposure": exposure_stats,
                "comparison": comparison_stats,
                "confounded_event_ids": confounded_ids,
                "overlap_event_ids": overlap_ids,
            },
        }

    def _extract_events(self, events_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(events_data, dict) and "events" in events_data:
            return events_data.get("events", [])
        return events_data if isinstance(events_data, list) else []

    def _extract_metrics(self, metrics_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(metrics_data, dict) and "metrics" in metrics_data:
            return metrics_data.get("metrics", [])
        return metrics_data if isinstance(metrics_data, list) else []

    def _index_metrics(self, metrics: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        index: Dict[str, List[Dict[str, Any]]] = {}
        for metric in metrics:
            event_id = metric.get("event_id")
            if not event_id:
                continue
            index.setdefault(event_id, []).append(metric)
        return index

    def _parse_timestamp(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            if value.endswith("Z") or value.endswith("z"):
                return datetime.fromisoformat(value[:-1] + "+00:00")
            raise

    def _parse_time_span(
        self,
        time_span: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        if not time_span:
            return None, None
        start = self._parse_timestamp(time_span["start_time"])
        end = self._parse_timestamp(time_span["end_time"])
        return start, end

    def _event_in_span(
        self,
        event: Dict[str, Any],
        span_start: Optional[datetime],
        span_end: Optional[datetime],
    ) -> bool:
        if span_start is None or span_end is None:
            return True
        event_start, _ = self._parse_event_times(event)
        return span_start <= event_start <= span_end

    def _parse_event_times(
        self,
        event: Dict[str, Any],
    ) -> Tuple[datetime, datetime]:
        start = self._parse_timestamp(event["start_time"])
        if "end_time" in event:
            end = self._parse_timestamp(event["end_time"])
        else:
            end = start + timedelta(minutes=self.default_event_duration_minutes)
        return start, end

    def _extract_context_tags(self, event: Dict[str, Any]) -> List[str]:
        notes = event.get("notes", "")
        marker = "Context tags:"
        if marker not in notes:
            return []
        tag_str = notes.split(marker, 1)[1]
        tags = [tag.strip().lower() for tag in tag_str.split(",") if tag.strip()]
        return tags

    def _matches_event_definition(
        self,
        event: Dict[str, Any],
        definition: Dict[str, Any],
    ) -> bool:
        if event.get("event_type") != definition.get("event_type"):
            return False
        selector = definition.get("selector", {})
        return self._match_selector(event, selector)

    def _matches_conditions(
        self,
        event: Dict[str, Any],
        conditions: List[Dict[str, Any]],
        time_zone: Optional[str],
    ) -> bool:
        for condition in conditions:
            if not self._match_condition(event, condition, time_zone):
                return False
        return True

    def _match_condition(
        self,
        event: Dict[str, Any],
        condition: Dict[str, Any],
        time_zone: Optional[str],
    ) -> bool:
        name = condition.get("name", "")
        if name in {"context_tag", "context", "context_tags"}:
            tags = self._extract_context_tags(event)
            return self._compare(condition.get("operator"), tags, condition.get("value"))

        if name == "time_of_day":
            event_start, _ = self._parse_event_times(event)
            event_time = event_start.timetz()
            event_minutes = event_time.hour * 60 + event_time.minute
            normalized_value = self._normalize_time_value(condition.get("value"))
            return self._compare(condition.get("operator"), event_minutes, normalized_value)

        value, unit = self._resolve_component(event, name)
        if value is None:
            return False

        expected_unit = condition.get("unit")
        if expected_unit and unit and expected_unit != unit:
            return False

        return self._compare(condition.get("operator"), value, condition.get("value"))

    def _match_selector(self, event: Dict[str, Any], selector: Dict[str, Any]) -> bool:
        component = selector.get("component")
        if not component:
            return False

        if selector.get("operator") == "exists":
            value, _ = self._resolve_component(event, component)
            return value is not None

        value, unit = self._resolve_component(event, component)
        if value is None:
            return False

        expected_unit = selector.get("unit")
        if expected_unit and unit and expected_unit != unit:
            return False

        return self._compare(selector.get("operator"), value, selector.get("value"))

    def _resolve_component(self, event: Dict[str, Any], component: str) -> Tuple[Optional[Any], Optional[str]]:
        component_lower = component.lower()
        if component_lower in {"label", "food_name"}:
            return event.get("label"), None
        if component_lower in {"event_type", "source", "annotation_quality"}:
            return event.get(component_lower), None
        if component_lower in {"start_time", "end_time"}:
            return event.get(component_lower), "datetime"

        if component_lower in {"context_tag", "context", "context_tags"}:
            return self._extract_context_tags(event), None

        for comp in event.get("exposure_components", []) or []:
            if comp.get("name") == component:
                return comp.get("value"), comp.get("unit")
        return None, None

    def _compare(self, operator: str, candidate: Any, value: Any) -> bool:
        if operator is None:
            return False

        if operator == "=":
            return self._equals(candidate, value)
        if operator == "<":
            return candidate < value
        if operator == ">":
            return candidate > value
        if operator == "<=":
            return candidate <= value
        if operator == ">=":
            return candidate >= value
        if operator == "between":
            if not isinstance(value, list) or len(value) != 2:
                return False
            lower = self._time_value(value[0])
            upper = self._time_value(value[1])
            candidate_value = self._time_value(candidate)
            return self._between(candidate_value, lower, upper)
        if operator == "in":
            if not isinstance(value, list):
                return False
            if isinstance(candidate, list):
                return any(self._equals(item, option) for item in candidate for option in value)
            return any(self._equals(candidate, option) for option in value)
        if operator == "exists":
            return candidate is not None
        return False

    def _equals(self, candidate: Any, value: Any) -> bool:
        if isinstance(candidate, str) and isinstance(value, str):
            return candidate.strip().lower() == value.strip().lower()
        if isinstance(candidate, list):
            return any(self._equals(item, value) for item in candidate)
        return candidate == value

    def _time_value(self, value: Any) -> Any:
        if isinstance(value, str) and ":" in value:
            parts = value.split(":")
            if len(parts) >= 2:
                return int(parts[0]) * 60 + int(parts[1])
        return value

    def _normalize_time_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._time_value(item) for item in value]
        return self._time_value(value)

    def _between(self, candidate: Any, lower: Any, upper: Any) -> bool:
        if lower is None or upper is None:
            return False
        if isinstance(candidate, (int, float)) and isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            if lower <= upper:
                return lower <= candidate <= upper
            return candidate >= lower or candidate <= upper
        return False

    def _find_confounded_events(
        self,
        events: List[Dict[str, Any]],
        isolation_minutes: int,
    ) -> List[str]:
        confounded = set()
        event_times = {}
        for event in events:
            start, end = self._parse_event_times(event)
            event_times[event["event_id"]] = (start, end)

        for event_id, (start, end) in event_times.items():
            window_start = start - timedelta(minutes=isolation_minutes)
            window_end = end + timedelta(minutes=isolation_minutes)
            for other_id, (other_start, other_end) in event_times.items():
                if other_id == event_id:
                    continue
                if other_start <= window_end and other_end >= window_start:
                    confounded.add(event_id)
                    break

        return sorted(confounded)

    def _evaluate_group(
        self,
        events: List[Dict[str, Any]],
        metrics_index: Dict[str, List[Dict[str, Any]]],
        question: Dict[str, Any],
        confounded_ids: List[str],
    ) -> Dict[str, Any]:
        metric_name = question["outcome"]["metric_name"]
        question_window = question["outcome"].get("window")
        matched_ids = [event["event_id"] for event in events]

        missing_metrics = []
        low_quality_metrics = []
        window_mismatches = []
        usable_ids = []

        for event in events:
            event_id = event["event_id"]
            if event_id in confounded_ids:
                continue

            metrics = [m for m in metrics_index.get(event_id, []) if m.get("metric_name") == metric_name]
            if not metrics:
                missing_metrics.append(event_id)
                continue

            metric = self._select_metric(metrics, question_window)
            if metric is None:
                window_mismatches.append(event_id)
                continue

            coverage = self._metric_coverage(metric)
            if coverage < self.min_metric_coverage:
                low_quality_metrics.append(event_id)
                continue

            usable_ids.append(event_id)

        confounded = [event_id for event_id in matched_ids if event_id in confounded_ids]

        return {
            "metric_name": metric_name,
            "matched_event_ids": matched_ids,
            "usable_event_ids": usable_ids,
            "confounded_event_ids": confounded,
            "missing_metric_event_ids": missing_metrics,
            "low_quality_metric_event_ids": low_quality_metrics,
            "window_mismatch_event_ids": window_mismatches,
        }

    def _select_metric(
        self,
        metrics: List[Dict[str, Any]],
        question_window: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if question_window is None:
            return metrics[0]
        for metric in metrics:
            if self._metric_window_matches(metric.get("window"), question_window):
                return metric
        return None

    def _metric_window_matches(
        self,
        metric_window: Optional[Dict[str, Any]],
        question_window: Dict[str, Any],
    ) -> bool:
        if not metric_window:
            return False
        if "relative_to" in metric_window:
            return (
                metric_window.get("relative_to") == question_window.get("relative_to")
                and metric_window.get("start_offset_minutes") == question_window.get("start_offset_minutes")
                and metric_window.get("end_offset_minutes") == question_window.get("end_offset_minutes")
            )
        return False

    def _metric_coverage(self, metric: Dict[str, Any]) -> float:
        if "coverage_ratio" in metric:
            return float(metric["coverage_ratio"])
        coverage = metric.get("quality_summary", {}).get("coverage_percentage")
        if coverage is None:
            return 1.0
        return float(coverage) / 100.0

    def _group_reasons(self, group_name: str, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        reasons = []
        matched = stats["matched_event_ids"]
        usable = stats["usable_event_ids"]
        metric_name = stats.get("metric_name")

        if not matched:
            reasons.append(self._reason(
                f"no_matching_{group_name}_events",
                f"No events match the {group_name} selector within the time span.",
                blocking=True,
            ))
            return reasons

        if stats["confounded_event_ids"]:
            reasons.append(self._reason(
                "confounded_context",
                f"{group_name.capitalize()} events are too close to other events.",
                blocking=len(usable) < self.min_events_per_group,
                affected_event_ids=stats["confounded_event_ids"],
            ))

        if stats["window_mismatch_event_ids"]:
            reasons.append(self._reason(
                "metric_window_mismatch",
                f"Metrics for {group_name} events do not match the requested window.",
                blocking=len(usable) < self.min_events_per_group,
                affected_event_ids=stats["window_mismatch_event_ids"],
            ))

        if stats["missing_metric_event_ids"]:
            code = "missing_baseline" if metric_name == "baseline_glucose" else "missing_metric"
            reasons.append(self._reason(
                code,
                f"Missing metric for {group_name} events.",
                blocking=len(usable) < self.min_events_per_group,
                affected_event_ids=stats["missing_metric_event_ids"],
            ))

        if stats["low_quality_metric_event_ids"]:
            reasons.append(self._reason(
                "low_metric_coverage",
                f"Low metric coverage for {group_name} events.",
                blocking=len(usable) < self.min_events_per_group,
                affected_event_ids=stats["low_quality_metric_event_ids"],
            ))

        if len(usable) < self.min_events_per_group:
            reasons.append(self._reason(
                f"insufficient_repeats_{group_name}",
                f"Need at least {self.min_events_per_group} usable {group_name} events, found {len(usable)}.",
                blocking=True,
                observed=len(usable),
                required=self.min_events_per_group,
            ))

        return reasons

    def _group_data_requirements(
        self,
        group_name: str,
        stats: Dict[str, Any],
        definition: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        requirements = []
        usable = stats["usable_event_ids"]
        missing_count = max(self.min_events_per_group - len(usable), 0)

        if not stats["matched_event_ids"]:
            requirements.append({
                "type": "collect_events",
                "group": group_name,
                "needed_count": self.min_events_per_group,
                "detail": f"Add events that match the {group_name} selector.",
                "selector": definition.get("selector"),
            })
            return requirements

        if missing_count > 0:
            requirements.append({
                "type": "collect_events",
                "group": group_name,
                "needed_count": missing_count,
                "detail": f"Collect at least {missing_count} more usable {group_name} events.",
                "selector": definition.get("selector"),
            })

        if stats["missing_metric_event_ids"]:
            requirements.append({
                "type": "compute_metrics",
                "group": group_name,
                "detail": "Compute outcome metrics for events missing metrics or improve CGM coverage.",
                "event_ids": stats["missing_metric_event_ids"],
            })

        if stats["low_quality_metric_event_ids"]:
            requirements.append({
                "type": "improve_cgm_coverage",
                "group": group_name,
                "detail": "Increase CGM coverage in the outcome window for low-coverage events.",
                "event_ids": stats["low_quality_metric_event_ids"],
            })

        if stats["window_mismatch_event_ids"]:
            requirements.append({
                "type": "recompute_metrics",
                "group": group_name,
                "detail": "Recompute metrics using the question's outcome window.",
                "event_ids": stats["window_mismatch_event_ids"],
            })

        if stats["confounded_event_ids"]:
            requirements.append({
                "type": "collect_isolated_events",
                "group": group_name,
                "detail": f"Add {group_name} events isolated by at least {self.min_isolation_minutes} minutes.",
                "event_ids": stats["confounded_event_ids"],
            })

        return requirements

    def _reason(
        self,
        code: str,
        detail: str,
        blocking: bool,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        reason = {
            "code": code,
            "detail": detail,
            "blocking": blocking,
        }
        reason.update(kwargs)
        return reason
