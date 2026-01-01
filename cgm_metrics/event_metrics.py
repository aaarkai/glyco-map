"""
CGM Event Metrics Calculator

Calculate windowed metrics around CGM events.

IMPORTANT: Events are CLAIMS, not ground truth measurements.
Metric reliability depends on event annotation quality and CGM data coverage.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import numpy.typing as npt


class CGMEventMetricsError(Exception):
    """Base exception for CGM event metrics operations."""
    pass


class CGMEventMetrics:
    """
    Calculate windowed metrics around CGM events.

    All metrics include metadata:
    - window definition (relative_to, start/end offsets)
    - coverage ratio (proportion of expected samples available)
    - computation version for reproducibility
    """

    # Metric computation versions (update when computation changes)
    VERSIONS = {
        "baseline_glucose": "1.0.0",
        "delta_peak": "1.0.0",
        "auc": "1.0.0",
        "time_to_peak": "1.0.0",
        "recovery_slope": "1.0.0",
    }

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def calculate_baseline_glucose(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any],
        window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": -30,
            "end_offset_minutes": 0
        }
    ) -> Dict[str, Any]:
        """
        Calculate baseline glucose (mean glucose in window before event).

        Args:
            cgm_data: CGM time series with samples
            event: Event annotation
            window: Time window definition

        Returns:
            Metric result with value, unit, window, coverage, and version

        Raises:
            CGMEventMetricsError: If window contains no valid data
        """
        window_samples, coverage_ratio, quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], window
        )

        if len(window_samples) == 0:
            raise CGMEventMetricsError(
                f"No CGM data in baseline window for event {event['event_id']}"
            )

        baseline = np.mean([sample["glucose_value"] for sample in window_samples])
        sampling_interval = cgm_data.get("sampling_interval_minutes", 5.0)

        expected_samples = self._calculate_expected_samples(window, sampling_interval)

        method_desc = (
            f"Mean glucose in {window['relative_to']} window "
            f"[{window['start_offset_minutes']}, {window['end_offset_minutes']}] minutes"
        )

        return {
            "event_id": event["event_id"],
            "metric_name": "baseline_glucose",
            "metric_version": self.VERSIONS["baseline_glucose"],
            "window": window,
            "value": float(baseline),
            "unit": cgm_data["unit"],
            "computed_at": datetime.now().isoformat(),
            "method": method_desc,
            "coverage_ratio": coverage_ratio,
            "quality_flags": quality_flags,
            "quality_summary": {
                "window_samples": len(window_samples),
                "expected_samples": expected_samples,
                "coverage_percentage": round(coverage_ratio * 100, 1)
            }
        }

    def calculate_delta_peak(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any],
        baseline_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": -30,
            "end_offset_minutes": 0
        },
        peak_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": 0,
            "end_offset_minutes": 180
        }
    ) -> Dict[str, Any]:
        """
        Calculate ΔPeak (peak glucose change from baseline).

        Args:
            cgm_data: CGM time series with samples
            event: Event annotation
            baseline_window: Window for baseline calculation
            peak_window: Window for peak detection

        Returns:
            Metric result with peak change from baseline

        Raises:
            CGMEventMetricsError: If baseline or peak cannot be calculated
        """
        baseline_result = self.calculate_baseline_glucose(
            cgm_data, event, baseline_window
        )
        baseline = baseline_result["value"]

        peak_samples, peak_coverage, peak_quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], peak_window
        )

        if len(peak_samples) == 0:
            raise CGMEventMetricsError(
                f"No CGM data in peak window for event {event['event_id']}"
            )

        peak_values = [sample["glucose_value"] for sample in peak_samples]
        peak_glucose = np.max(peak_values)
        peak_time_index = np.argmax(peak_values)
        peak_time = peak_samples[peak_time_index]["timestamp"]

        delta_peak = peak_glucose - baseline

        expected_samples = self._calculate_expected_samples(peak_window, cgm_data.get("sampling_interval_minutes", 5.0))

        method_desc = (
            f"Peak glucose in event window minus baseline glucose. "
            f"Baseline from [{baseline_window['start_offset_minutes']}, {baseline_window['end_offset_minutes']}] minutes, "
            f"peak from [{peak_window['start_offset_minutes']}, {peak_window['end_offset_minutes']}] minutes."
        )

        all_quality_flags = list(set(baseline_result.get("quality_flags", []) + peak_quality_flags))

        return {
            "event_id": event["event_id"],
            "metric_name": "delta_peak",
            "metric_version": self.VERSIONS["delta_peak"],
            "window": {
                "baseline_window": baseline_window,
                "peak_window": peak_window
            },
            "value": float(delta_peak),
            "unit": cgm_data["unit"],
            "computed_at": datetime.now().isoformat(),
            "method": method_desc,
            "coverage_ratio": peak_coverage,
            "quality_flags": all_quality_flags,
            "quality_summary": {
                "peak_glucose": float(peak_glucose),
                "baseline_glucose": float(baseline),
                "peak_time": peak_time,
                "window_samples": len(peak_samples),
                "expected_samples": expected_samples,
                "coverage_percentage": round(peak_coverage * 100, 1)
            }
        }

    def calculate_iAUC(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any],
        baseline_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": -30,
            "end_offset_minutes": 0
        },
        auc_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": 0,
            "end_offset_minutes": 180
        }
    ) -> Dict[str, Any]:
        """
        Calculate incremental Area Under the Curve (iAUC).

        AUC is calculated relative to baseline, positive area only.
        Uses trapezoid rule for numerical integration.

        Args:
            cgm_data: CGM time series with samples
            event: Event annotation
            baseline_window: Window for baseline calculation
            auc_window: Window for AUC calculation

        Returns:
            Metric result with iAUC value and unit (mg/dL * minutes)

        Raises:
            CGMEventMetricsError: If insufficient data for calculation
        """
        baseline_result = self.calculate_baseline_glucose(
            cgm_data, event, baseline_window
        )
        baseline = baseline_result["value"]

        auc_samples, auc_coverage, auc_quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], auc_window
        )

        if len(auc_samples) < 2:
            raise CGMEventMetricsError(
                f"Insufficient CGM data for iAUC calculation for event {event['event_id']}"
            )

        values = np.array([s["glucose_value"] for s in auc_samples])
        times = [datetime.fromisoformat(s["timestamp"]) for s in auc_samples]

        differences = values - baseline
        positive_differences = np.maximum(differences, 0)

        auc = 0.0
        for i in range(len(positive_differences) - 1):
            time_delta = (times[i+1] - times[i]).total_seconds() / 60.0
            avg_value = (positive_differences[i] + positive_differences[i+1]) / 2.0
            auc += avg_value * time_delta

        expected_samples = self._calculate_expected_samples(auc_window, cgm_data.get("sampling_interval_minutes", 5.0))

        method_desc = (
            f"Incremental Area Under the Curve above baseline. "
            f"Calculated using trapezoid rule with {len(auc_samples)} samples in window "
            f"[{auc_window['start_offset_minutes']}, {auc_window['end_offset_minutes']}] minutes."
        )

        unit = f"{cgm_data['unit']} * minutes"

        all_quality_flags = list(set(baseline_result.get("quality_flags", []) + auc_quality_flags))

        return {
            "event_id": event["event_id"],
            "metric_name": "iAUC",
            "metric_version": self.VERSIONS["auc"],
            "window": {
                "baseline_window": baseline_window,
                "auc_window": auc_window
            },
            "value": float(auc),
            "unit": unit,
            "computed_at": datetime.now().isoformat(),
            "method": method_desc,
            "coverage_ratio": auc_coverage,
            "quality_flags": all_quality_flags,
            "quality_summary": {
                "baseline_glucose": float(baseline),
                "positive_area": float(auc),
                "window_samples": len(auc_samples),
                "expected_samples": expected_samples,
                "coverage_percentage": round(auc_coverage * 100, 1)
            }
        }

    def calculate_time_to_peak(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any],
        window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": 0,
            "end_offset_minutes": 180
        }
    ) -> Dict[str, Any]:
        """
        Calculate time to peak glucose from event start (in minutes).

        Args:
            cgm_data: CGM time series with samples
            event: Event annotation
            window: Time window for peak detection

        Returns:
            Metric result with time to peak (minutes)
        """
        window_samples, coverage_ratio, quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], window
        )

        if len(window_samples) == 0:
            raise CGMEventMetricsError(
                f"No CGM data in time-to-peak window for event {event['event_id']}"
            )

        event_start_time = datetime.fromisoformat(event["start_time"])

        values = [sample["glucose_value"] for sample in window_samples]
        peak_index = np.argmax(values)
        peak_value = values[peak_index]
        peak_time = datetime.fromisoformat(window_samples[peak_index]["timestamp"])

        time_to_peak_minutes = (peak_time - event_start_time).total_seconds() / 60.0

        expected_samples = self._calculate_expected_samples(window, cgm_data.get("sampling_interval_minutes", 5.0))

        method_desc = (
            f"Time from event start to maximum glucose value in window. "
            f"Event start: {event['start_time']}, peak time: {peak_time.isoformat()}."
        )

        return {
            "event_id": event["event_id"],
            "metric_name": "time_to_peak",
            "metric_version": self.VERSIONS["time_to_peak"],
            "window": window,
            "value": float(time_to_peak_minutes),
            "unit": "minutes",
            "computed_at": datetime.now().isoformat(),
            "method": method_desc,
            "coverage_ratio": coverage_ratio,
            "quality_flags": quality_flags,
            "quality_summary": {
                "peak_glucose": float(peak_value),
                "peak_time": peak_time.isoformat(),
                "event_start": event["start_time"],
                "window_samples": len(window_samples),
                "expected_samples": expected_samples,
                "coverage_percentage": round(coverage_ratio * 100, 1)
            }
        }

    def calculate_recovery_slope(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any],
        peak_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": 0,
            "end_offset_minutes": 180
        },
        recovery_window: Dict[str, Any] = {
            "relative_to": "event_start",
            "start_offset_minutes": 120,
            "end_offset_minutes": 240
        }
    ) -> Dict[str, Any]:
        """
        Calculate recovery slope (rate of glucose decline after peak).

        Positive slope indicates recovery, negative indicates continued rise,
        values near zero indicate no clear recovery pattern.

        Args:
            cgm_data: CGM time series with samples
            event: Event annotation
            peak_window: Window for peak detection
            recovery_window: Window for recovery measurement

        Returns:
            Metric result with recovery slope (unit per minute)
        """
        peak_samples, peak_coverage, peak_quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], peak_window
        )

        recovery_samples, recovery_coverage, recovery_quality_flags = self._extract_window_samples(
            cgm_data, event["start_time"], recovery_window
        )

        if len(peak_samples) == 0:
            raise CGMEventMetricsError(
                f"No CGM data in peak window for event {event['event_id']}"
            )
        if len(recovery_samples) < 2:
            raise CGMEventMetricsError(
                f"Insufficient data in recovery window for event {event['event_id']}"
            )

        peak_values = [sample["glucose_value"] for sample in peak_samples]
        peak_index = np.argmax(peak_values)
        peak_value = peak_values[peak_index]
        peak_time = datetime.fromisoformat(peak_samples[peak_index]["timestamp"])

        recovery_values = [sample["glucose_value"] for sample in recovery_samples]
        recovery_times = [datetime.fromisoformat(sample["timestamp"]) for sample in recovery_samples]

        center_time = recovery_times[len(recovery_times) // 2]

        recovery_times_min = [(t - center_time).total_seconds() / 60.0 for t in recovery_times]
        slope, intercept = np.polyfit(recovery_times_min, recovery_values, 1)

        start_recovery_value = slope * recovery_times_min[0] + intercept
        end_recovery_value = slope * recovery_times_min[-1] + intercept

        return_percentage = None
        if start_recovery_value > 0:
            return_percentage = (peak_value - end_recovery_value) / (peak_value - start_recovery_value) * 100

        expected_peak_samples = self._calculate_expected_samples(peak_window, cgm_data.get("sampling_interval_minutes", 5.0))
        expected_recovery_samples = self._calculate_expected_samples(recovery_window, cgm_data.get("sampling_interval_minutes", 5.0))

        method_desc = (
            f"Linear regression slope during recovery window after peak glucose. "
            f"Slope > 0 indicates declining glucose (recovery), "
            f"slope < 0 indicates continued rise."
        )

        all_quality_flags = list(set(peak_quality_flags + recovery_quality_flags))

        return {
            "event_id": event["event_id"],
            "metric_name": "recovery_slope",
            "metric_version": self.VERSIONS["recovery_slope"],
            "window": {
                "peak_window": peak_window,
                "recovery_window": recovery_window
            },
            "value": float(slope),
            "unit": f"{cgm_data['unit']} per minute",
            "computed_at": datetime.now().isoformat(),
            "method": method_desc,
            "coverage_ratio": (peak_coverage + recovery_coverage) / 2.0,
            "quality_flags": all_quality_flags,
            "quality_summary": {
                "peak_glucose": float(peak_value),
                "recovery_start": float(start_recovery_value),
                "recovery_end": float(end_recovery_value),
                "return_toward_baseline_percentage": float(return_percentage) if return_percentage is not None else None,
                "peak_window_samples": len(peak_samples),
                "peak_expected_samples": expected_peak_samples,
                "recovery_window_samples": len(recovery_samples),
                "recovery_expected_samples": expected_recovery_samples,
                "peak_coverage_percentage": round(peak_coverage * 100, 1),
                "recovery_coverage_percentage": round(recovery_coverage * 100, 1)
            }
        }

    def _extract_window_samples(
        self,
        cgm_data: Dict[str, Any],
        reference_time: str,
        window: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], float, List[str]]:
        """
        Extract samples within a time window relative to reference time.

        Args:
            cgm_data: CGM time series data
            reference_time: ISO timestamp reference point
            window: Window definition (relative_to, start_offset, end_offset)

        Returns:
            Tuple of (sample_list, coverage_ratio, quality_flags)
            coverage_ratio: proportion of expected samples actually present
            quality_flags: list of quality issues detected
        """
        ref_time = datetime.fromisoformat(reference_time)

        window_start = ref_time + timedelta(minutes=window["start_offset_minutes"])
        window_end = ref_time + timedelta(minutes=window["end_offset_minutes"])

        window_samples = []

        for sample in cgm_data["samples"]:
            sample_time = datetime.fromisoformat(sample["timestamp"])
            if window_start <= sample_time <= window_end:
                window_samples.append(sample)

        sampling_interval = cgm_data.get("sampling_interval_minutes", 5.0)
        expected_samples = self._calculate_expected_samples(window, sampling_interval)

        coverage_ratio = len(window_samples) / expected_samples if expected_samples > 0 else 1.0
        coverage_ratio = min(coverage_ratio, 1.0)

        quality_flags = []
        if coverage_ratio < 0.7:
            quality_flags.append("low_coverage")
        if coverage_ratio < 1.0:
            quality_flags.append("missing_data")

        for sample in window_samples:
            if "quality_flags" in sample and sample["quality_flags"]:
                if "artifact" in sample["quality_flags"] or "sensor_error" in sample["quality_flags"]:
                    quality_flags.append("interpolated")
                    break

        return window_samples, coverage_ratio, list(set(quality_flags))

    def _calculate_expected_samples(
        self,
        window: Dict[str, Any],
        sampling_interval: float
    ) -> int:
        """
        Calculate expected number of samples in a window.

        Args:
            window: Window definition
            sampling_interval: Sampling interval in minutes

        Returns:
            Expected number of samples
        """
        window_duration = window["end_offset_minutes"] - window["start_offset_minutes"]
        expected_samples = int(window_duration / sampling_interval) + 1
        return max(expected_samples, 0)

    def calculate_all_metrics(
        self,
        cgm_data: Dict[str, Any],
        event: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Calculate all available metrics for an event.

        Args:
            cgm_data: CGM time series data
            event: Event annotation

        Returns:
            List of metric results for the event
        """
        metrics = []

        try:
            baseline = self.calculate_baseline_glucose(cgm_data, event)
            metrics.append(baseline)
        except CGMEventMetricsError as e:
            self._logger.warning(f"Failed to calculate baseline for event {event['event_id']}: {e}")

        try:
            delta_peak = self.calculate_delta_peak(cgm_data, event)
            metrics.append(delta_peak)
        except CGMEventMetricsError as e:
            self._logger.warning(f"Failed to calculate delta_peak for event {event['event_id']}: {e}")

        try:
            iauc = self.calculate_iAUC(cgm_data, event)
            metrics.append(iauc)
        except CGMEventMetricsError as e:
            self._logger.warning(f"Failed to calculate iAUC for event {event['event_id']}: {e}")

        try:
            ttp = self.calculate_time_to_peak(cgm_data, event)
            metrics.append(ttp)
        except CGMEventMetricsError as e:
            self._logger.warning(f"Failed to calculate time_to_peak for event {event['event_id']}: {e}")

        try:
            recovery = self.calculate_recovery_slope(cgm_data, event)
            metrics.append(recovery)
        except CGMEventMetricsError as e:
            self._logger.warning(f"Failed to calculate recovery_slope for event {event['event_id']}: {e}")

        return metrics
