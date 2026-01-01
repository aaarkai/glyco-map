# Minimal Domain Entities (Conceptual Spec)

This system is an n-of-1 causal reasoning workflow over CGM data. The entities below are the smallest set needed to define questions, evaluate answerability, and report evidence without mixing concerns.

## Raw Signal
- Purpose: Represent the primary CGM time series as measured by the device.
- Required fields:
  - subject_id
  - device_id or sensor_id
  - timestamp (with timezone or offset)
  - glucose_value
  - units
  - sampling_interval or sample_index
  - quality_flags (e.g., missing, interpolated, sensor error)
- Must not contain:
  - Derived features or metrics
  - Event annotations or causal labels
  - Imputed values without explicit flags

## Event / Intervention
- Purpose: Describe time-stamped exposures that may affect glucose (e.g., meals).
- Required fields:
  - subject_id
  - event_type (e.g., meal, snack)
  - start_time (and end_time or duration if applicable)
  - exposure_components with units (e.g., carbohydrate_g, fat_g)
  - source (manual, app, import)
  - annotation_quality or uncertainty
- Must not contain:
  - CGM outcomes or response metrics
  - Causal effect estimates
  - Post-hoc labels based on outcomes

## Context / Condition
- Purpose: Capture background factors that define analysis strata or confounders.
- Required fields:
  - subject_id
  - time_window (start/end)
  - factor_name (e.g., sleep, activity, illness, medication)
  - factor_value and units (if numeric)
  - source and measurement_quality
- Must not contain:
  - Outcome measurements from CGM
  - Effect estimates or conclusions
  - Unbounded narratives without time scope

## Metric
- Purpose: Define a computable summary of the raw signal over a window.
- Required fields:
  - metric_name
  - formal definition or formula
  - required inputs (signal fields, preprocessing)
  - time_window definition relative to an event or clock time
  - units
- Must not contain:
  - Causal claims or inference logic
  - Event annotations embedded as data
  - Subject-specific interpretations

## Hypothesis / Question
- Purpose: Specify a causal query to test within a single subject.
- Required fields:
  - subject_id
  - exposure_definition (what varies, how measured)
  - outcome_metric (by metric_name and window)
  - counterfactual or comparison condition
  - inclusion/exclusion criteria and time span
  - explicit assumptions (e.g., no overlapping exposures)
- Must not contain:
  - Evidence summaries or effect estimates
  - Diagnostics or answerability decisions
  - Clinical or population-level claims

## Evidence
- Purpose: Record the data-derived support for a specific hypothesis.
- Required fields:
  - question_id
  - data_provenance (raw signal and events used)
  - estimation_method
  - effect_estimate with uncertainty
  - diagnostics and sensitivity results
  - answerability status and failed checks (if any)
- Must not contain:
  - New hypotheses or alternative questions
  - Unscoped recommendations or advice
  - Claims beyond the defined subject and time span
