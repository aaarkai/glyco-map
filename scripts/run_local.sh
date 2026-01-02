#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${1:-data}"
OUTPUT_ROOT="${2:-output}"
TIMEZONE="${TIMEZONE:-Asia/Shanghai}"
UNIT="${UNIT:-mmol/L}"
EVENTS_FALLBACK_TEXT="${EVENTS_TEXT:-$DATA_DIR/events.txt}"
EVENTS_FALLBACK_JSON="${EVENTS_JSON:-$DATA_DIR/events.json}"
QUESTION_PATH="${QUESTION_PATH:-$DATA_DIR/question.json}"
SUBJECT_ID="${SUBJECT_ID:-}"
DEVICE_ID="${DEVICE_ID:-}"

files=()
while IFS= read -r -d '' file; do
  files+=("$file")
done < <(find "$DATA_DIR" -maxdepth 1 -type f -name '*.xlsx' -print0)

if [ "${#files[@]}" -eq 0 ]; then
  echo "No XLSX files found in $DATA_DIR"
  exit 1
fi

mkdir -p "$OUTPUT_ROOT"

subject_args=()
device_args=()
question_args=()
if [ -n "$SUBJECT_ID" ]; then
  subject_args=(--subject-id "$SUBJECT_ID")
fi
if [ -n "$DEVICE_ID" ]; then
  device_args=(--device-id "$DEVICE_ID")
fi
if [ -f "$QUESTION_PATH" ]; then
  question_args=(--question-file "$QUESTION_PATH")
fi

for file in "${files[@]}"; do
  stem=$(basename "$file" .xlsx)
  output_dir="$OUTPUT_ROOT/$stem"

  events_args=()
  events_text="$DATA_DIR/$stem.txt"
  events_json="$DATA_DIR/$stem.json"

  if [ -f "$events_text" ]; then
    events_args=(--events-text "$events_text")
  elif [ -f "$events_json" ]; then
    events_args=(--events-file "$events_json")
  elif [ -f "$EVENTS_FALLBACK_TEXT" ]; then
    events_args=(--events-text "$EVENTS_FALLBACK_TEXT")
  elif [ -f "$EVENTS_FALLBACK_JSON" ]; then
    events_args=(--events-file "$EVENTS_FALLBACK_JSON")
  fi

  python -m cgm_pipeline.cli \
    "$file" \
    "$output_dir" \
    "${events_args[@]:-}" \
    "${question_args[@]:-}" \
    "${subject_args[@]:-}" \
    "${device_args[@]:-}" \
    --timezone "$TIMEZONE" \
    --unit "$UNIT" \
    --pretty \
    --markdown \
    --verbose

done

export OUTPUT_ROOT
python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

output_root = Path(os.environ["OUTPUT_ROOT"])
cases = []

for path in sorted(output_root.iterdir()):
    if not path.is_dir():
        continue
    cgm_path = path / "cgm.json"
    if not cgm_path.exists():
        continue
    end_time = None
    sanity_path = path / "sanity.json"
    if sanity_path.exists():
        sanity = json.loads(sanity_path.read_text(encoding="utf-8"))
        end_time = sanity.get("summary", {}).get("end_time")
    cases.append({
        "title": path.name,
        "path": path.name,
        "end_time": end_time,
    })

def parse_time(value):
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0

cases.sort(key=lambda item: parse_time(item.get("end_time")), reverse=True)
payload = {
    "schema_version": "1.0.0",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "cases": cases,
}

output_root.mkdir(parents=True, exist_ok=True)
(output_root / "cases.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY

printf '\nDone. Outputs in %s and cases.json generated.\n' "$OUTPUT_ROOT"
