# CGM Map Pipeline

N-of-1 CGM analysis pipeline for personal data. This is not medical advice, not a population model, and not a CGM dashboard.

## Quick start (local)

```bash
python -m cgm_pipeline.cli data/your.xlsx output/ \
  --events-text data/your.txt \
  --timezone Asia/Shanghai \
  --markdown \
  --pretty \
  --verbose

python -m http.server 8000
```

Open `http://localhost:8000/web/` and select your case.

## Data layout

Required:
- `data/<name>.xlsx`

Optional (per file, preferred):
- `data/<name>.txt` (events text)
- `data/<name>.json` (events JSON)

Optional (fallback if per-file is missing):
- `data/events.txt`
- `data/events.json`

Optional (global):
- `data/question.json`

Event text format (one line per event):
```
YYYY-MM-DD HH:MM label
```

If multiple events share the same timestamp, they are merged into one event with labels joined by ` / `.

## Outputs

For each input file, the pipeline writes:
- `output/<name>/cgm.json`
- `output/<name>/sanity.json`
- `output/<name>/metrics.json`
- `output/<name>/event_signals.json`
- `output/<name>/report.json`
- `output/<name>/report.md`

The workflow also writes:
- `output/cases.json` (case index for the web viewer)

## Web viewer

`web/index.html` reads:
- `cases.json` to list available cases
- `cgm.json`, `events.json`, `metrics.json`, `event_signals.json` per case

Interactions:
- Click an event (or its metric card) to highlight baseline and response windows on the timeline.
- Threshold fill shows where glucose exceeds 7.8 (mmol/L) within the response window.

## GitHub Actions + Pages

Push changes under `data/` to trigger the workflow. It will:
- Process every `data/*.xlsx`
- Match events by file name
- Publish `web/index.html` plus case data to GitHub Pages

Enable Pages for this repo:
- Settings -> Pages -> Source: GitHub Actions

Your site will be at:
- `https://<user>.github.io/<repo>/`

## Units

The default unit is `mmol/L`.

To use mg/dL instead:
- Pass `--unit mg/dL` to the CLI
- Or set the workflow input `unit` to `mg/dL`

## Core CLI

Run the full pipeline on a single file:
```bash
python -m cgm_pipeline.cli data/your.xlsx output/ \
  --timezone Asia/Shanghai \
  --events-text data/your.txt
```

