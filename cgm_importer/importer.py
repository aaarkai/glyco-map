"""
Core CGM XLSX importer functionality.
"""

import json
import pandas as pd
import numpy as np
from datetime import timedelta
from typing import Dict, List, Any, Optional
import hashlib


class CGM_XLSX_Importer:
    """
    Importer for CGM data from XLSX files with Chinese column names.
    Converts to CGM time series schema format.
    """

    def __init__(self):
        self.required_columns = ["血糖时间", "血糖值"]  # timestamp, glucose_value

    def read_xlsx(self, filepath: str) -> pd.DataFrame:
        """
        Read CGM data from XLSX file.

        Args:
            filepath: Path to the XLSX file

        Returns:
            pandas DataFrame with CGM data

        Raises:
            ValueError: If required columns are missing
        """
        try:
            df = pd.read_excel(filepath)
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")

        # Check for required columns
        missing_cols = set(self.required_columns) - set(df.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        # Select only required columns and rename for clarity
        df = df[self.required_columns].copy()
        df = df.rename(columns={
            "血糖时间": "timestamp",
            "血糖值": "glucose_value"
        })

        # Convert timestamp to datetime
        try:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        except Exception as e:
            raise ValueError(f"Failed to parse timestamps: {e}")

        # Convert glucose_value to numeric, preserving non-numeric values as NaN
        # This handles values like "异常" (abnormal) which are sensor errors
        original_values = df["glucose_value"].copy()
        df["glucose_value"] = pd.to_numeric(df["glucose_value"], errors="coerce")

        # Create quality flags column for non-numeric original values
        quality_flags = []
        for i, (is_numeric, original) in enumerate(zip(df["glucose_value"].notna(), original_values)):
            if not is_numeric:
                quality_flags.append(["sensor_error"])
            else:
                quality_flags.append([])
        df["quality_flags"] = quality_flags

        # Remove rows with NaN values (both timestamp and glucose_value)
        # This removes rows that couldn't be parsed as timestamps or numeric glucose values
        df = df.dropna().reset_index(drop=True)

        # Check for duplicate timestamps before sorting
        if df["timestamp"].duplicated().any():
            duplicate_count = df["timestamp"].duplicated().sum()
            raise ValueError(
                f"Detected {duplicate_count} duplicate timestamps. "
                f"Each timestamp must be unique for proper interval calculation."
            )

        # Sort by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        return df

    def detect_sampling_interval(self, timestamps: pd.Series) -> float:
        """
        Infer sampling interval from timestamps using robust statistical methods.

        Args:
            timestamps: Series of datetime timestamps

        Returns:
            Sampling interval in minutes

        Raises:
            ValueError: If intervals are inconsistent
        """
        if len(timestamps) < 2:
            raise ValueError("At least 2 samples required to infer sampling interval")

        # Check for duplicates first
        if timestamps.duplicated().any():
            duplicate_count = timestamps.duplicated().sum()
            raise ValueError(
                f"Detected {duplicate_count} duplicate timestamps. "
                f"Each timestamp must be unique for proper interval calculation."
            )

        # Calculate differences in minutes
        timedeltas = timestamps.diff().dropna()
        intervals = timedeltas.dt.total_seconds() / 60.0 if hasattr(timedeltas, 'dt') else timedeltas.total_seconds() / 60.0

        if len(intervals) == 0:
            raise ValueError("No valid intervals found")

        # Guard against zero intervals (shouldn't happen after duplicate check, but be safe)
        zero_intervals = sum(1 for x in intervals if x < 0.001)
        if zero_intervals > 0:
            raise ValueError(
                f"Detected {zero_intervals} zero-length intervals. "
                f"Timestamps may be unsorted."
            )

        # Use median for robustness against outliers
        median_interval = float(np.median(intervals))

        # Check if intervals are reasonably consistent (within 20% of median)
        consistent = all(
            abs(x - median_interval) / median_interval < 0.2
            for x in intervals
        )

        if not consistent:
            # Check for common CGM patterns (e.g., minute-wise vs 5/15 minutes)
            rounded_intervals = np.round(intervals)
            unique_intervals, counts = np.unique(rounded_intervals, return_counts=True)
            most_common_idx = np.argmax(counts)

            if len(unique_intervals) > 1:
                # Use most common interval
                median_interval = unique_intervals[most_common_idx]
            else:
                raise ValueError(
                    f"Inconsistent sampling intervals detected: "
                    f"ranges from {intervals.min():.1f} to {intervals.max():.1f} minutes"
                )

        return float(median_interval)

    def detect_artifacts(self, glucose_values: pd.Series, unit: str = "mg/dL") -> List[List[str]]:
        """
        Detect common CGM sensor artifacts and quality issues.

        Args:
            glucose_values: Series of glucose values
            unit: Glucose unit ('mg/dL' or 'mmol/L')

        Returns:
            List of quality flag lists for each sample
        """
        quality_flags = [[] for _ in range(len(glucose_values))]

        # Define artifact detection thresholds based on unit
        # 3 mmol/L ≈ 54 mg/dL - this is a very large physiologic jump
        if unit == "mmol/L":
            jump_threshold = 3.0  # mmol/L
        else:  # mg/dL
            jump_threshold = 54.0  # mg/dL

        for i, value in enumerate(glucose_values):
            flags = []

            # Check for large single-sample jumps
            # Only flag if value change is physically impossible
            if i > 0 and i < len(glucose_values) - 1:
                prev_value = glucose_values.iloc[i-1]
                change_current = abs(value - prev_value)

                if change_current > jump_threshold:
                    # Check if it's followed by reversal (ie, correction back toward previous)
                    next_value = glucose_values.iloc[i+1]
                    # If next_value moves at least 70% of the way back to previous value
                    distance_back = abs(next_value - prev_value)
                    if distance_back < change_current * 0.3:
                        flags.append("artifact")

            # Check for flat readings (same value 3+ times)
            if i >= 2:
                if (glucose_values.iloc[i-2] == glucose_values.iloc[i-1] == value):
                    flags.append("artifact")

            quality_flags[i] = flags

        return quality_flags

    def convert_to_schema(
        self,
        df: pd.DataFrame,
        subject_id: str,
        device_id: str,
        timezone: str,
        unit: str = "mg/dL"
    ) -> Dict[str, Any]:
        """
        Convert pandas DataFrame to CGM time series schema format.

        Args:
            df: DataFrame with 'timestamp' and 'glucose_value' columns
            subject_id: Unique identifier for the subject
            device_id: Device identifier
            timezone: IANA timezone name (e.g., 'America/Los_Angeles')
            unit: Glucose value unit ('mg/dL' or 'mmol/L')

        Returns:
            Dictionary conforming to cgm-time-series.schema.json
        """
        # Infer sampling interval
        sampling_interval = self.detect_sampling_interval(df["timestamp"])

        # Detect artifacts
        detected_flags = self.detect_artifacts(df["glucose_value"], unit)

        # Get pre-existing quality flags from read_xlsx
        pre_flags = df.get("quality_flags", [[] for _ in range(len(df))])

        # Generate series ID based on actual content for provenance
        # Hash includes timestamps and values to ensure uniqueness per dataset
        content_for_hash = []
        for _, row in df.iterrows():
            content_for_hash.append(f"{row['timestamp'].isoformat()}:{row['glucose_value']:.6f}")

        series_hash = hashlib.sha256(
            f"{subject_id}_{device_id}_{';'.join(content_for_hash)}".encode()
        ).hexdigest()[:16]
        series_id = f"cgm_{series_hash}"

        # Convert timestamps to ISO format with timezone
        timestamps_iso = [
            ts.tz_localize(timezone).isoformat()
            if ts.tz is None
            else ts.tz_convert(timezone).isoformat()
            for ts in df["timestamp"]
        ]

        # Build samples array
        samples = []
        for i, (_, row) in enumerate(df.iterrows()):
            sample = {
                "timestamp": timestamps_iso[i],
                "glucose_value": float(row["glucose_value"]),
                "sample_index": i
            }

            # Combine quality flags
            all_flags = set()
            all_flags.update(pre_flags[i])
            all_flags.update(detected_flags[i])

            if all_flags:
                sample["quality_flags"] = list(all_flags)

            samples.append(sample)

        # Construct schema document
        schema_doc = {
            "schema_version": "1.0.0",
            "series_id": series_id,
            "subject_id": subject_id,
            "device_id": device_id,
            "time_zone": timezone,
            "unit": unit,
            "sampling_interval_minutes": sampling_interval,
            "samples": samples
        }

        return schema_doc

    def write_schema(self, schema_data: Dict[str, Any], output_path: str) -> None:
        """
        Write schema data to JSON file.

        Args:
            schema_data: Schema-compliant dictionary
            output_path: Output file path
        """
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(schema_data, f, indent=2, ensure_ascii=False)