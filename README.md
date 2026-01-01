# CGM XLSX Importer

A Python package for importing Continuous Glucose Monitor (CGM) data from Excel files with Chinese column names (血糖时间, 血糖值) and converting them into a JSON schema format.

## Features

- **No assumptions about timezone**: Requires explicit timezone input
- **Statistical sampling interval detection**: Robustly infers sampling intervals from timestamps
- **Preserves original values**: No smoothing or modification of raw data
- **Sensor artifact detection**: Annotates possible artifacts but does not remove them
- **Comprehensive error handling**: Handles missing values and invalid data
- **Standards-compliant**: Generates JSON conforming to the CGM time series schema

## Installation

```bash
pip install -r requirements.txt
```

Requirements:
- pandas >= 2.0
- openpyxl >= 3.1
- numpy (usually installed with pandas)

## Usage

### Importing CGM Data

Basic usage with required parameters:

```bash
python -m cgm_importer.cli input.xlsx \
  --subject-id user1 \
  --device-id libre2-123 \
  --timezone America/Los_Angeles
```

With all options:

```bash
python -m cgm_importer.cli input.xlsx \
  --output output.json \
  --subject-id user1 \
  --device-id libre2-123 \
  --timezone Asia/Shanghai \
  --unit mmol/L \
  --validate \
  --pretty
```

### Creating Meal/Intervention Events

**IMPORTANT: Events are CLAIMS about exposures, not ground truth measurements.**

Create events interactively:

```bash
python -m cgm_events.cli events.json \
  --subject-id user1 \
  --timezone America/Los_Angeles \
  --multiple
```

Create a single event with all parameters:

```bash
python -m cgm_events.cli events.json \
  --subject-id user1 \
  --timezone America/Los_Angeles \
  --event-type meal \
  --label "pizza dinner" \
  --start-time "2024-01-01T18:30:00-08:00" \
  --end-time "2024-01-01T19:00:00-08:00" \
  --carbs 75 \
  --tags "dinner,restaurant,post_exercise" \
  --notes "ate 3 slices"
```

Event fields:
- **start_time**: When the event started (required)
- **end_time**: When the event ended (optional)
- **label**: Free-text description (e.g., "pizza dinner")
- **estimated_carbs**: Estimated carbs in grams (optional)
- **context_tags**: Context for analysis (e.g., dinner, restaurant, post_exercise)
- **source**: How the annotation was created (manual/app/import/api)
- **annotation_quality**: Subjective quality score 0-1

### Generating Signal Sanity Report

After importing CGM data, generate a signal sanity report:

```bash
python -m cgm_importer.sanity_cli input.json
```

With options:

```bash
python -m cgm_importer.sanity_cli input.json \
  --output report.json \
  --pretty \
  --no-summary
```

The report analyzes:
- **Coverage**: Data completeness and gaps
- **Sampling Regularity**: Consistency of time intervals
- **Extreme Values**: Minimum/maximum glucose values
- **Suspicious Changes**: Rapid drops or spikes
- **Quality Flags**: Distribution of flagged samples

### Parameters

- `input`: Path to the XLSX file (required)
- `-o, --output`: Output JSON file path (default: `<input>.json`)
- `-s, --subject-id`: Subject identifier (required)
- `-d, --device-id`: CGM device identifier (required)
- `-z, --timezone`: IANA timezone name (e.g., 'America/Los_Angeles'). Can also be set via `CGM_TZ` environment variable.
- `-u, --unit`: Glucose value unit - 'mg/dL' or 'mmol/L' (default: mg/dL)
- `--validate`: Validate output against schema (requires jsonschema package)
- `--pretty`: Pretty print JSON output

### Examples

```bash
# Import CGM data
python -m cgm_importer.cli cgm_data.xlsx \
  -s subject_001 \
  -d dexcom_g7_sn12345 \
  -z America/New_York

# Generate sanity report from imported data
python -m cgm_importer.sanity_cli cgm_data.json \
  -o sanity_report.json \
  --pretty

# Process with timezone from environment variable
export CGM_TZ=Europe/London
python -m cgm_importer.cli cgm_data.xlsx \
  -s subject_002 \
  -d libre_3_sn67890

# Validate output against schema
python -m cgm_importer.cli cgm_data.xlsx \
  -s subject_003 \
  -d eversense_sn11111 \
  -z Asia/Tokyo \
  --validate \
  --pretty
```

## Schema Output

The importer generates JSON files conforming to the CGM time series schema, including:

- Schema version and metadata
- Subject and device identifiers
- Timezone information
- Sampling interval (automatically detected)
- Array of samples with timestamps, glucose values, and quality flags

Example:

```json
{
  "schema_version": "1.0.0",
  "series_id": "cgm_9e144d99a32e9de8",
  "subject_id": "subject1",
  "device_id": "SiSensing-LT2506MPT5",
  "time_zone": "Asia/Shanghai",
  "unit": "mmol/L",
  "sampling_interval_minutes": 5.0,
  "samples": [
    {
      "timestamp": "2025-12-24T23:29:00+08:00",
      "glucose_value": 6.0,
      "sample_index": 0
    },
    {
      "timestamp": "2025-12-24T23:34:00+08:00",
      "glucose_value": 5.9,
      "sample_index": 1,
      "quality_flags": ["artifact"]
    }
  ]
}
```

## Quality Flags

The importer annotates samples with quality flags when anomalies are detected:

- `sensor_error`: Non-numeric glucose values (e.g., "异常" in source data)
- `artifact`: Rapid glucose jumps followed by reversal, or flat readings (3+ identical values)

## Event Annotations

**IMPORTANT DESIGN PRINCIPLE:** Events (meals, interventions) are **CLAIMS** about exposures, not ground truth measurements.

### Key Distinctions

**Events are CLAIMS:**
- Subject-reported or observer-annotated
- Subjective quality and timing
- May contain recall bias
- Annotation quality varies by source

**CGM Data are MEASUREMENTS:**
- Device-recorded timestamps
- Objective values (with sensor artifacts flagged)
- Mechanical sampling intervals

### Implications for Analysis

1. **Question answerability** depends on event annotation quality
2. **Causal inference** must account for uncertainty in both timing and dose
3. **Low-quality annotations** may not support reliable conclusions
4. **Validation** should compare claims against external sources when possible

The system validates events and warns about:
- Low annotation quality (< 0.5)
- Missing exposure components (e.g., no carb estimates)
- Very short events (< 5 minutes)
- Manual entry sources (vs. app/import)
- Missing context tags

## Sanity Report Output

The sanity report generates JSON with detailed quality analysis:

```json
{
  "report_version": "1.0.0",
  "series_metadata": {
    "series_id": "cgm_9e144d99a32e9de8",
    "subject_id": "subject1",
    "device_id": "SiSensing-LT2506MPT5"
  },
  "coverage": {
    "coverage_percentage": 98.3,
    "missing_intervals": 22,
    "large_gaps": 1
  },
  "sampling_regularity": {
    "mean_interval_minutes": 5.1,
    "cv_interval": 0.608,
    "is_regular": false
  },
  "extreme_values": {
    "min_value": 2.2,
    "max_value": 11.3,
    "extreme_low": 28,
    "extreme_high": 0
  },
  "suspicious_changes": {
    "suspicious_drops": [...],
    "suspicious_spikes": [],
    "total_suspicious": 1
  },
  "quality_flags": {
    "total_flagged_samples": 75,
    "flag_breakdown": {"artifact": 75}
  }
}
```

## Testing

Run the test suites:

```bash
# Test importer
python -m test_importer

# Test sanity report generator
python test_sanity_report.py
```

## Architecture

The package is structured into:

### CGM Import and Analysis
- `cgm_importer/importer.py`: Core import logic with artifact detection
- `cgm_importer/cli.py`: Command-line interface for importing
- `cgm_importer/sanity_report.py`: Signal quality analysis
- `cgm_importer/sanity_cli.py`: CLI for generating sanity reports
- `test_importer.py`: Test suite for importer

### Event Annotation
- `cgm_events/events.py`: Event creation and validation
- `cgm_events/cli.py`: CLI for creating meal/intervention events
- `test_events.py`: Test suite for events

### Schemas
- `schemas/cgm-time-series.schema.json`: CGM time series format
- `schemas/meal-intervention-events.schema.json`: Event annotation format
- Additional schemas for derived metrics and hypothesis evaluation

## License

This is an n-of-1 experimental system, not a population model, not medical advice, and not a CGM dashboard.
