# Product

This repository builds an n-of-1 experimental system that uses a person's CGM data plus a small number of meal annotations to determine which causal questions about food–glucose response are answerable with the current data.

## What counts as a question
A question is a precise, causal, within-person query about a food exposure and a CGM-derived outcome, with a defined time window and comparison.

A valid question must specify:
- Exposure: a food or meal feature (e.g., "50 g available carbohydrate", "meal containing 20 g fat") and its timing.
- Outcome: a CGM-derived metric (e.g., incremental AUC over 2 hours, peak delta glucose, time above threshold) and its window.
- Counterfactual/comparison: relative to no meal, a different meal, or a different level of the same feature.
- Scope: single person, specified date range, and the CGM data source.

Non-questions include descriptive summaries, population claims, or any query without a clear exposure, outcome, and counterfactual.

## What counts as answerable
A question is answerable if, given current data and assumptions, the system can estimate the causal effect with bounded uncertainty and known limitations.

Minimum criteria:
- Observability: required CGM samples and meal annotations exist for the relevant window.
- Identifiability: assumptions needed to estimate the causal effect are explicit and not contradicted by the data (e.g., no overlapping unobserved co-exposures in the window).
- Adequate support: enough instances or variation to estimate the effect without extrapolation (defined per question).
- Diagnostic checks: the system can compute diagnostics that do not fail (e.g., missingness, overlap, timing alignment, sensitivity tests).

If any criterion fails, the system marks the question as not answerable, with the failed criteria reported.

## What the system explicitly refuses to claim
The system does not claim:
- Generalization beyond the individual or beyond the observed time span.
- Medical advice, diagnosis, or safety guidance.
- Population-level effects or causal mechanisms.
- Certainty when assumptions are untestable or diagnostics fail.
- Effects for foods or exposures not present in the annotations.

## Artifacts the system outputs
For each candidate question, the system outputs:
- A machine-readable question specification (exposure, outcome, window, counterfactual, assumptions).
- An answerability decision with a checklist of criteria and failed checks if any.
- If answerable, an effect estimate with uncertainty and diagnostics.
- A provenance log linking to the exact CGM and annotation records used.
- A limitations statement enumerating assumptions and sensitivity results.
