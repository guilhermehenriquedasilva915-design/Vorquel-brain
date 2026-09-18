from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .analyzer import DEFAULT_MAX_FILE_BYTES, analyze_file


def _iter_json_files(path: Path):
    if path.is_file():
        if path.suffix.lower() == ".json":
            yield path
        return
    yield from sorted(file for file in path.rglob("*.json") if file.is_file())


def _summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = Counter(report["risk_decision"] for report in reports)
    severities = Counter(report["max_severity"] for report in reports)
    rules = Counter(
        finding["rule_id"]
        for report in reports
        for finding in report.get("findings", [])
    )
    return {
        "files_analyzed": len(reports),
        "risk_decisions": dict(sorted(decisions.items())),
        "max_severities": dict(sorted(severities.items())),
        "finding_rules": dict(sorted(rules.items())),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Statically analyze n8n workflow JSON without executing it."
    )
    parser.add_argument("path", type=Path, help="Workflow JSON file or directory to scan")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_BYTES / (1024 * 1024),
        help="Maximum workflow JSON size in MiB (default: 5)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_file_mb <= 0:
        raise SystemExit("--max-file-mb must be greater than zero")
    if not args.path.exists():
        raise SystemExit(f"Path does not exist: {args.path}")

    max_bytes = int(args.max_file_mb * 1024 * 1024)
    reports = [
        analyze_file(path, max_file_bytes=max_bytes).to_dict()
        for path in _iter_json_files(args.path)
    ]
    payload = {
        "schema_version": "0.1",
        "trust_boundary": "RAW_UNTRUSTED_INPUT_NEVER_EXECUTED",
        "summary": _summary(reports),
        "reports": reports,
    }
    output_text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n", encoding="utf-8")
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
