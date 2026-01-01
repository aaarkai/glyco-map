#!/usr/bin/env python3
"""
Pipeline CLI: XLSX import -> sanity report -> event metrics -> answerability.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from cgm_importer.importer import CGM_XLSX_Importer
from cgm_importer.sanity_report import CGMSanityReport
from cgm_metrics.cli import calculate_event_metrics
from cgm_questions.answerability import QuestionAnswerabilityEvaluator
from cgm_events.text_parser import CGMEventTextParser
import re


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        raise ValueError(f"Failed to load JSON from {path}: {exc}")


def write_json(path: Path, payload: dict, pretty: bool) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2 if pretty else None, ensure_ascii=False)


def derive_device_id(path: Path) -> str:
    stem = path.stem
    parts = stem.split("-")
    if len(parts) > 1 and re.match(r"^\d+(?:\.\d+)+$", parts[-1]):
        return "-".join(parts[:-1])
    return stem


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run CGM analysis pipeline from XLSX to answerability report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cgm_pipeline.cli data.xlsx out/ \\
    --subject-id user1 --device-id libre2-001 --timezone Asia/Shanghai
        """,
    )

    parser.add_argument("xlsx_file", type=str, help="Path to CGM XLSX file")
    parser.add_argument("output_dir", type=str, help="Directory for pipeline outputs")

    parser.add_argument("--events-file", type=str, help="Path to events JSON file (optional)")
    parser.add_argument("--events-text", type=str, help="Path to events text file (optional)")
    parser.add_argument("--events-text-type", default="meal", help="Event type for parsed text events")
    parser.add_argument("--question-file", type=str, help="Path to question JSON file (optional)")

    parser.add_argument("--subject-id", help="Subject identifier (optional)")
    parser.add_argument("--device-id", help="CGM device identifier (optional)")
    parser.add_argument("--timezone", required=True, help="IANA timezone name")
    parser.add_argument("--unit", choices=["mg/dL", "mmol/L"], default="mg/dL")
    parser.add_argument("--metric-set-id", type=str, help="Metric set identifier")

    parser.add_argument("--min-events", type=int, default=2, help="Minimum events per group")
    parser.add_argument("--min-metric-coverage", type=float, default=0.7, help="Minimum metric coverage ratio")
    parser.add_argument("--min-isolation-minutes", type=int, default=30, help="Minimum isolation minutes")

    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")
    parser.add_argument("--verbose", action="store_true", help="Print progress details")
    parser.add_argument("--markdown", action="store_true", help="Write a Markdown summary report")

    return parser


def _write_markdown_report(path: Path, report: dict) -> None:
    summary = report.get("summary", {})
    answerability = report.get("answerability") or {}
    reasons = answerability.get("reasons", [])
    requirements = answerability.get("data_requirements", [])

    lines = [
        "# CGM Question Report",
        "",
        f"- Generated: {report.get('generated_at', 'unknown')}",
        f"- Series ID: {summary.get('series_id', 'unknown')}",
        f"- Total samples: {summary.get('total_samples', 0)}",
        f"- Coverage: {summary.get('coverage_percentage', 'unknown')}",
        f"- Total metrics: {summary.get('total_metrics', 0)}",
        f"- Answerable: {summary.get('answerable')}",
        "",
        "## Blocking Reasons",
    ]

    blocking = [r for r in reasons if r.get("blocking")]
    if not blocking:
        lines.append("- None")
    else:
        for reason in blocking:
            lines.append(f"- {reason.get('code')}: {reason.get('detail')}")

    lines.append("")
    lines.append("## All Reasons")
    if not reasons:
        lines.append("- None")
    else:
        for reason in reasons:
            lines.append(f"- {reason.get('code')}: {reason.get('detail')}")

    lines.append("")
    lines.append("## Data Requirements")
    if not requirements:
        lines.append("- None")
    else:
        for req in requirements:
            detail = req.get("detail", "unspecified")
            lines.append(f"- {req.get('type')}: {detail}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx_file)
    output_dir = Path(args.output_dir)

    if not xlsx_path.exists():
        print(f"Error: Input file not found: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    events_path = Path(args.events_file) if args.events_file else None
    events_text_path = Path(args.events_text) if args.events_text else None
    question_path = Path(args.question_file) if args.question_file else None

    for path in (events_path, events_text_path, question_path):
        if path is not None and not path.exists():
            print(f"Error: Input file not found: {path}", file=sys.stderr)
            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    subject_id = args.subject_id or "subject"
    device_id = args.device_id or derive_device_id(xlsx_path)

    if args.verbose:
        print("Importing CGM XLSX...", file=sys.stderr)

    importer = CGM_XLSX_Importer()
    df = importer.read_xlsx(str(xlsx_path))
    cgm_data = importer.convert_to_schema(
        df,
        subject_id=subject_id,
        device_id=device_id,
        timezone=args.timezone,
        unit=args.unit,
    )

    cgm_path = output_dir / "cgm.json"
    write_json(cgm_path, cgm_data, args.pretty)

    if args.verbose:
        print("Generating sanity report...", file=sys.stderr)

    reporter = CGMSanityReport()
    sanity_report = reporter.generate_report(cgm_data)
    sanity_path = output_dir / "sanity.json"
    write_json(sanity_path, sanity_report, args.pretty)

    metrics_data = None
    metrics_path = None
    events_data = None
    events_path_used = None

    if events_text_path is not None:
        if args.verbose:
            print("Parsing events from text...", file=sys.stderr)
        parser_engine = CGMEventTextParser()
        events = parser_engine.parse_file(
            str(events_text_path),
            subject_id=args.subject_id,
            timezone=args.timezone,
            event_type=args.events_text_type,
        )
        from cgm_events.events import CGMEventCreator

        creator = CGMEventCreator()
        events_data = creator.create_events_collection(
            subject_id=args.subject_id,
            timezone=args.timezone,
            events=events,
            collection_notes=f"Parsed from {events_text_path.name}",
        )
        events_path_used = output_dir / "events.json"
        write_json(events_path_used, events_data, args.pretty)

    if events_path is not None and events_data is None:
        if args.verbose:
            print("Loading events...", file=sys.stderr)

        events_data = load_json(events_path)
        events_path_used = events_path

    if events_data is not None:
        if args.verbose:
            print("Computing metrics...", file=sys.stderr)

        metric_set_id = args.metric_set_id or f"metric_set_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        metrics_data = calculate_event_metrics(
            cgm_data,
            events_data,
            metric_set_id,
            verbose=args.verbose,
        )
        metrics_path = output_dir / "metrics.json"
        write_json(metrics_path, metrics_data, args.pretty)

    answerability = None
    answerability_path = None

    if question_path is not None and metrics_data is not None and events_data is not None:
        if args.verbose:
            print("Evaluating answerability...", file=sys.stderr)

        question = load_json(question_path)
        evaluator = QuestionAnswerabilityEvaluator(
            min_events_per_group=args.min_events,
            min_metric_coverage=args.min_metric_coverage,
            min_isolation_minutes=args.min_isolation_minutes,
        )
        answerability = evaluator.evaluate(question, events_data, metrics_data)
        answerability_path = output_dir / "answerability.json"
        write_json(answerability_path, answerability, args.pretty)

    report = {
        "report_version": "1.0.0",
        "generated_at": datetime.now().isoformat(),
        "inputs": {
            "xlsx_file": str(xlsx_path),
            "events_file": str(events_path_used) if events_path_used is not None else None,
            "events_text_file": str(events_text_path) if events_text_path is not None else None,
            "question_file": str(question_path) if question_path is not None else None,
            "subject_id": subject_id,
            "device_id": device_id,
            "time_zone": args.timezone,
            "unit": args.unit,
        },
        "outputs": {
            "cgm_json": str(cgm_path),
            "sanity_json": str(sanity_path),
            "events_json": str(events_path_used) if events_path_used is not None else None,
            "metrics_json": str(metrics_path) if metrics_path is not None else None,
            "answerability_json": str(answerability_path) if answerability_path is not None else None,
        },
        "summary": {
            "series_id": cgm_data.get("series_id"),
            "total_samples": len(cgm_data.get("samples", [])),
            "sampling_interval_minutes": cgm_data.get("sampling_interval_minutes"),
            "coverage_percentage": sanity_report["coverage"].get("coverage_percentage"),
            "total_metrics": len(metrics_data.get("metrics", [])) if metrics_data else 0,
            "answerable": answerability.get("answerable") if answerability else None,
            "blocking_reasons": [
                reason for reason in answerability.get("reasons", [])
                if reason.get("blocking")
            ] if answerability else [],
        },
        "answerability": answerability,
    }

    report_path = output_dir / "report.json"
    write_json(report_path, report, args.pretty)

    if args.markdown:
        report_md = output_dir / "report.md"
        _write_markdown_report(report_md, report)

    if args.verbose:
        print(f"Pipeline completed. Report: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
