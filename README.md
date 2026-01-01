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

### Parsing Events from Text

Parse a simple text file where each line is:

```
YYYY-MM-DD HH:MM <label>
```

Example:

```bash
python -m cgm_events.text_cli data/events.txt data/events.json \
  --subject-id subject_001 \
  --timezone Asia/Shanghai \
  --event-type meal \
  --pretty
```

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

### Calculating Event Metrics

Calculate windowed metrics around meal/intervention events:

```bash
python -m cgm_metrics.cli cgm_data.json events.json \
  --metric-set-id experiment_week_1 \
  --output metrics.json
```

Each metric includes:
- **Window definition**: Time window relative to event start/end
- **Coverage ratio**: Proportion of expected samples available
- **Computation version**: Semantic version for reproducibility

**Example output fields per metric:**
- `event_id`: Links metric to specific event
- `metric_name`: One of [baseline_glucose, delta_peak, iAUC, time_to_peak, recovery_slope]
- `value`: Computed metric value
- `unit`: Unit of measurement
- `coverage_ratio`: 0.0 to 1.0 (1.0 = all samples present)
- `quality_flags`: e.g., ["low_coverage", "missing_data"]
- `quality_summary`: Additional details for interpretation

**Metric Coverage Guidelines:**
- > 90%: Excellent, highly reliable
- 70-90%: Good, acceptable for most analyses
- 50-70%: Marginal, use with caution
- < 50%: Poor, exclude from analysis

### Pipeline CLI

Run a full pipeline from XLSX to answerability report:

```bash
python -m cgm_pipeline.cli data.xlsx output/ \
  --subject-id subject_001 \
  --device-id dexcom_g7_sn12345 \
  --timezone Asia/Shanghai \
  --unit mg/dL \
  --markdown \
  --pretty \
  --verbose
```

Optional inputs:

```bash
python -m cgm_pipeline.cli data.xlsx output/ \
  --events-file data/events.json \
  --question-file data/question.json \
  --subject-id subject_001 \
  --device-id dexcom_g7_sn12345 \
  --timezone Asia/Shanghai
```

Parse event text inline:

```bash
python -m cgm_pipeline.cli data.xlsx output/ \
  --events-text data/events.txt \
  --events-text-type meal \
  --subject-id subject_001 \
  --device-id dexcom_g7_sn12345 \
  --timezone Asia/Shanghai
```

Outputs (in `output/`):
- `cgm.json`: CGM time series schema
- `sanity.json`: Signal sanity report
- `metrics.json`: Derived metrics per event
- `answerability.json`: Structured answerability evaluation
- `report.json`: Summary report
- `report.md`: Markdown summary (when `--markdown` is used)

The GitHub Actions workflow in `.github/workflows/pipeline.yml` runs this pipeline.
Events/questions are optional; when provided, it can publish `report.json`/`report.md`
to a separate GitHub Pages repo.

### Automated GitHub Actions Pipeline

Recommended upload location:

- `data/cgm.xlsx` (required)
- `data/events.txt` (optional, one event per line)
- `data/question.json` (optional)

When you push changes under `data/`, the workflow triggers automatically.
Set these repository variables in GitHub Actions:

- `SUBJECT_ID`
- `DEVICE_ID`
- `TIMEZONE` (optional, defaults to Asia/Shanghai)
- `PUBLISH_REPO` (e.g., `aaarkai/aaarkai.github.io`)
- `PUBLISH_PATH` (e.g., `ecg_map`)

Also add a `PUBLISH_TOKEN` secret with write access to the pages repo.

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

# Create meal events
python -m cgm_events.cli events.json \
  -s subject_001 \
  -z America/New_York \
  --multiple

# Calculate event metrics
python -m cgm_metrics.cli cgm_data.json events.json \
  --metric-set-id week_1_experiment \
  --output metrics.json \
  --verbose

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

### Event Metrics
- `cgm_metrics/event_metrics.py`: Per-event windowed metrics calculation
  - **baseline_glucose**: Mean glucose in pre-event window
  - **delta_peak**: Peak change from baseline (ΔPeak)
  - **iAUC**: Incremental area under curve above baseline
  - **time_to_peak**: Minutes from event start to peak glucose
  - **recovery_slope**: Rate of glucose decline post-peak
- `cgm_metrics/cli.py`: CLI for calculating metrics from CGM and events
  - Each metric includes: window definition, coverage ratio, computation version
  - Handles missing data and annotates quality flags
- `test_metrics.py`: Comprehensive test suite for all metrics

### Schemas
- `schemas/cgm-time-series.schema.json`: CGM time series format
- `schemas/meal-intervention-events.schema.json`: Event annotation format
- Additional schemas for derived metrics and hypothesis evaluation

## License

This is an n-of-1 experimental system, not a population model, not medical advice, and not a CGM dashboard.
