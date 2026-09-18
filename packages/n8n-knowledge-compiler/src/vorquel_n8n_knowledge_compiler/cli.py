from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .compiler import compile_knowledge_item

DEFAULT_MAX_WORKFLOW_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_ANALYSIS_BYTES = 25 * 1024 * 1024


def _normalized(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _read_untrusted_json(path: Path, *, max_bytes: int, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"{label} symlink input is not allowed")

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"unable to stat {label}: {exc.__class__.__name__}") from exc

    if size > max_bytes:
        raise ValueError(f"{label} exceeds configured size limit ({max_bytes} bytes)")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"unable to read {label}: {exc.__class__.__name__}") from exc

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{label} JSON must be an object")
    return payload


def _select_report(payload: dict[str, Any], source_path: str) -> dict[str, Any]:
    if "risk_decision" in payload:
        return payload

    reports = payload.get("reports")
    if not isinstance(reports, list):
        raise ValueError("analysis payload must be a report or contain a reports list")

    wanted = _normalized(source_path)
    matches: list[dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        candidate = _normalized(str(report.get("source_path", "")))
        if candidate == wanted or candidate.endswith("/" + wanted):
            matches.append(report)

    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one analysis report for {source_path!r}, got {len(matches)}"
        )
    return matches[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile an untrusted n8n workflow into structured knowledge."
    )
    parser.add_argument("workflow", type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--max-workflow-mb",
        type=float,
        default=DEFAULT_MAX_WORKFLOW_BYTES / (1024 * 1024),
    )
    parser.add_argument(
        "--max-analysis-mb",
        type=float,
        default=DEFAULT_MAX_ANALYSIS_BYTES / (1024 * 1024),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_workflow_mb <= 0 or args.max_analysis_mb <= 0:
        raise SystemExit("size limits must be greater than zero")

    try:
        workflow = _read_untrusted_json(
            args.workflow,
            max_bytes=int(args.max_workflow_mb * 1024 * 1024),
            label="workflow",
        )
        analysis_payload = _read_untrusted_json(
            args.analysis,
            max_bytes=int(args.max_analysis_mb * 1024 * 1024),
            label="analysis",
        )
        report = _select_report(analysis_payload, args.source_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    raw = args.workflow.read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()
    analyzed_sha = str(report.get("sha256", ""))
    if analyzed_sha and analyzed_sha != source_sha256:
        raise SystemExit("workflow SHA-256 does not match the selected analyzer report")

    item = compile_knowledge_item(
        workflow,
        report,
        source_repo=args.source_repo,
        source_commit=args.source_commit,
        source_path=args.source_path,
        source_sha256=source_sha256,
    )
    output = json.dumps(
        item,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if args.pretty else None,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
