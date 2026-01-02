"""
Event signal evaluation.

Combine CGM event metrics into red/yellow/green/gray status signals with
explanatory triggers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np


MMOL_TO_MGDL = 18.0


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _convert_threshold(value_mmol: float, unit: str) -> float:
    if unit == "mmol/L":
        return value_mmol
    return value_mmol * MMOL_TO_MGDL


def _format_metric_value(value: float, unit: Optional[str]) -> str:
    if unit:
        return f"{value:.2f} {unit}"
    return f"{value:.2f}"


def _format_percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def _percentile(values: List[float], p: float) -> float:
    return float(np.percentile(np.array(values, dtype=float), p))


METRIC_LABELS = {
    "delta_peak": "ΔPeak",
    "iAUC": "iAUC_0-120",
    "nadir_glucose": "Nadir",
    "recovery_slope": "Recovery slope",
    "peak_glucose": "Peak glucose",
    "coverage_ratio": "Coverage",
}


@dataclass
class Trigger:
    metric: str
    value: Optional[float]
    threshold: Optional[float]
    comparison: str
    basis: str
    severity: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "basis": self.basis,
            "severity": self.severity,
            "message": self.message,
        }


class EventSignalEvaluator:
    def __init__(
        self,
        coverage_soft: float = 0.85,
        history_size: int = 30,
        min_history: int = 10,
    ) -> None:
        self.coverage_soft = coverage_soft
        self.history_size = history_size
        self.min_history = min_history

    def evaluate(
        self,
        cgm_data: Dict[str, Any],
        events_data: Dict[str, Any],
        metrics_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        unit = cgm_data.get("unit", "mg/dL")
        events = events_data.get("events", [])
        metrics = metrics_data.get("metrics", [])

        events_sorted = sorted(events, key=lambda e: _parse_time(e["start_time"]))

        metrics_by_event: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for metric in metrics:
            event_id = metric.get("event_id")
            metric_name = metric.get("metric_name")
            if not event_id or not metric_name:
                continue
            metrics_by_event.setdefault(event_id, {})[metric_name] = metric

        history: Dict[str, List[float]] = {
            "delta_peak": [],
            "iAUC": [],
            "nadir_glucose": [],
            "recovery_slope": [],
        }

        signals = []

        for event in events_sorted:
            event_id = event.get("event_id")
            event_metrics = metrics_by_event.get(event_id, {})

            required = ["delta_peak", "iAUC", "nadir_glucose", "recovery_slope"]
            missing = [name for name in required if name not in event_metrics]

            coverage_values = [
                event_metrics[name].get("coverage_ratio")
                for name in required
                if name in event_metrics and event_metrics[name].get("coverage_ratio") is not None
            ]
            coverage_ratio = min(coverage_values) if coverage_values else None

            triggers: List[Trigger] = []

            if missing:
                for name in missing:
                    label = METRIC_LABELS.get(name, name)
                    message = f"missing metric: {label}"
                    triggers.append(
                        Trigger(
                            metric=name,
                            value=None,
                            threshold=None,
                            comparison="missing",
                            basis="missing_metric",
                            severity="soft",
                            message=message,
                        )
                    )

            if coverage_ratio is None:
                triggers.append(
                    Trigger(
                        metric="coverage_ratio",
                        value=None,
                        threshold=self.coverage_soft,
                        comparison="missing",
                        basis="coverage_soft",
                        severity="soft",
                        message="coverage unavailable",
                    )
                )
            elif coverage_ratio < self.coverage_soft:
                message = (
                    f"{METRIC_LABELS['coverage_ratio']}="
                    f"{_format_percent(coverage_ratio)} < "
                    f"{_format_percent(self.coverage_soft)} (soft)"
                )
                triggers.append(
                    Trigger(
                        metric="coverage_ratio",
                        value=coverage_ratio,
                        threshold=self.coverage_soft,
                        comparison="<",
                        basis="coverage_soft",
                        severity="soft",
                        message=message,
                    )
                )

            if missing or coverage_ratio is None or coverage_ratio < self.coverage_soft:
                status = "gray"
                signals.append(
                    {
                        "event_id": event_id,
                        "status": status,
                        "coverage_ratio": coverage_ratio,
                        "triggers": [trigger.to_dict() for trigger in triggers],
                        "metric_values": self._collect_metric_values(event_metrics),
                    }
                )
                continue

            hard_triggers: List[Trigger] = []
            soft_triggers: List[Trigger] = []

            peak_threshold = _convert_threshold(7.8, unit)
            peak_glucose = (
                event_metrics["delta_peak"]
                .get("quality_summary", {})
                .get("peak_glucose")
            )
            if peak_glucose is not None and peak_glucose > peak_threshold:
                message = (
                    f"{METRIC_LABELS['peak_glucose']}="
                    f"{_format_metric_value(peak_glucose, unit)} > "
                    f"{_format_metric_value(peak_threshold, unit)} (hard)"
                )
                hard_triggers.append(
                    Trigger(
                        metric="peak_glucose",
                        value=float(peak_glucose),
                        threshold=float(peak_threshold),
                        comparison=">",
                        basis="hard",
                        severity="hard",
                        message=message,
                    )
                )

            nadir_threshold = _convert_threshold(3.9, unit)
            nadir_value = event_metrics["nadir_glucose"]["value"]
            if nadir_value < nadir_threshold:
                message = (
                    f"{METRIC_LABELS['nadir_glucose']}="
                    f"{_format_metric_value(nadir_value, unit)} < "
                    f"{_format_metric_value(nadir_threshold, unit)} (hard)"
                )
                hard_triggers.append(
                    Trigger(
                        metric="nadir_glucose",
                        value=float(nadir_value),
                        threshold=float(nadir_threshold),
                        comparison="<",
                        basis="hard",
                        severity="hard",
                        message=message,
                    )
                )

            personal_triggers = self._evaluate_personal_thresholds(
                event_metrics, history, unit
            )
            for trigger in personal_triggers:
                if trigger.severity == "hard":
                    hard_triggers.append(trigger)
                else:
                    soft_triggers.append(trigger)

            triggers.extend(hard_triggers)
            triggers.extend(soft_triggers)

            if hard_triggers:
                status = "red"
            elif soft_triggers:
                status = "yellow"
            else:
                status = "green"

            signals.append(
                {
                    "event_id": event_id,
                    "status": status,
                    "coverage_ratio": coverage_ratio,
                    "triggers": [trigger.to_dict() for trigger in triggers],
                    "metric_values": self._collect_metric_values(event_metrics),
                }
            )

            self._update_history(history, event_metrics, coverage_ratio)

        signal_set_id = f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        return {
            "schema_version": "1.0.0",
            "signal_set_id": signal_set_id,
            "subject_id": cgm_data.get("subject_id"),
            "time_zone": cgm_data.get("time_zone"),
            "series_id": cgm_data.get("series_id"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "coverage_soft": self.coverage_soft,
            "history_size": self.history_size,
            "min_history": self.min_history,
            "events": signals,
        }

    def _collect_metric_values(
        self, metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Optional[float]]:
        values = {}
        for name in ["delta_peak", "iAUC", "nadir_glucose", "recovery_slope"]:
            if name in metrics:
                values[name] = float(metrics[name]["value"])
        peak_glucose = metrics.get("delta_peak", {}).get("quality_summary", {}).get("peak_glucose")
        if peak_glucose is not None:
            values["peak_glucose"] = float(peak_glucose)
        return values

    def _evaluate_personal_thresholds(
        self,
        event_metrics: Dict[str, Dict[str, Any]],
        history: Dict[str, List[float]],
        unit: str,
    ) -> List[Trigger]:
        triggers: List[Trigger] = []

        def eval_high(metric_name: str) -> None:
            values = history[metric_name][-self.history_size :]
            if len(values) < self.min_history:
                return
            value = float(event_metrics[metric_name]["value"])
            p90 = _percentile(values, 90)
            p75 = _percentile(values, 75)
            label = METRIC_LABELS.get(metric_name, metric_name)
            if value >= p90:
                message = (
                    f"{label}={_format_metric_value(value, unit)} > "
                    f"{_format_metric_value(p90, unit)} (personal P90)"
                )
                triggers.append(
                    Trigger(
                        metric=metric_name,
                        value=value,
                        threshold=p90,
                        comparison=">",
                        basis="personal_p90",
                        severity="hard",
                        message=message,
                    )
                )
            elif value >= p75:
                message = (
                    f"{label}={_format_metric_value(value, unit)} > "
                    f"{_format_metric_value(p75, unit)} (personal P75)"
                )
                triggers.append(
                    Trigger(
                        metric=metric_name,
                        value=value,
                        threshold=p75,
                        comparison=">",
                        basis="personal_p75",
                        severity="soft",
                        message=message,
                    )
                )

        def eval_low(metric_name: str) -> None:
            values = history[metric_name][-self.history_size :]
            if len(values) < self.min_history:
                return
            value = float(event_metrics[metric_name]["value"])
            p10 = _percentile(values, 10)
            p25 = _percentile(values, 25)
            label = METRIC_LABELS.get(metric_name, metric_name)
            if value <= p10:
                message = (
                    f"{label}={_format_metric_value(value, unit)} < "
                    f"{_format_metric_value(p10, unit)} (personal P10)"
                )
                triggers.append(
                    Trigger(
                        metric=metric_name,
                        value=value,
                        threshold=p10,
                        comparison="<",
                        basis="personal_p10",
                        severity="hard",
                        message=message,
                    )
                )
            elif value <= p25:
                message = (
                    f"{label}={_format_metric_value(value, unit)} < "
                    f"{_format_metric_value(p25, unit)} (personal P25)"
                )
                triggers.append(
                    Trigger(
                        metric=metric_name,
                        value=value,
                        threshold=p25,
                        comparison="<",
                        basis="personal_p25",
                        severity="soft",
                        message=message,
                    )
                )

        eval_high("delta_peak")
        eval_high("iAUC")
        eval_high("recovery_slope")
        eval_low("nadir_glucose")

        return triggers

    def _update_history(
        self,
        history: Dict[str, List[float]],
        event_metrics: Dict[str, Dict[str, Any]],
        coverage_ratio: Optional[float],
    ) -> None:
        if coverage_ratio is None or coverage_ratio < self.coverage_soft:
            return
        for metric_name in history.keys():
            metric = event_metrics.get(metric_name)
            if metric is None:
                continue
            value = metric.get("value")
            if value is None:
                continue
            history[metric_name].append(float(value))
