from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from vorquel_n8n_knowledge_compiler.cli import (
    DEFAULT_MAX_WORKFLOW_BYTES,
    _read_untrusted_json,
)
from vorquel_n8n_knowledge_compiler.compiler import compile_knowledge_item

SELECTION = {
    "INFO": 8,
    "MEDIUM": 8,
    "HIGH": 5,
    "CRITICAL": 3,
}

EXPECTED_ROLE = {
    "INFO": "REFERENCE_PATTERN",
    "MEDIUM": "STRUCTURE_REFERENCE_RESTRICTED",
    "HIGH": "QUARANTINED_REFERENCE",
    "CRITICAL": "SECURITY_EXAMPLE",
}

CODE_NODE_TYPES = {
    "n8n-nodes-base.code",
    "n8n-nodes-base.function",
    "n8n-nodes-base.functionItem",
}
COMMAND_NODE_TYPES = {
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.ssh",
}


def _relative_source_path(report: dict[str, Any], corpus_dir: Path) -> str:
    raw_path = Path(str(report.get("source_path", "")))
    try:
        relative = raw_path.resolve().relative_to(corpus_dir.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError(f"report path is outside corpus root: {raw_path}") from exc
    return relative.as_posix()


def _flatten_strings(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _flatten_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _flatten_strings(child)
    elif isinstance(value, str):
        yield value


def _source_credential_strings(workflow: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for node in workflow.get("nodes", []):
        if not isinstance(node, dict):
            continue
        credentials = node.get("credentials")
        if not isinstance(credentials, dict):
            continue
        for value in _flatten_strings(credentials):
            if len(value) >= 8:
                values.add(value)
    return values


def _source_executable_strings(workflow: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for node in workflow.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        parameters = node.get("parameters", {})
        if not isinstance(parameters, (dict, list)):
            continue
        for value in _flatten_strings(parameters):
            stripped = value.strip()
            is_expression = stripped.startswith("=") or "{{" in stripped or "}}" in stripped
            if node_type in CODE_NODE_TYPES | COMMAND_NODE_TYPES or is_expression:
                if len(value) >= 16:
                    values.add(value)
    return values


def _contains_key(value: Any, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        if forbidden_key in value:
            return True
        return any(_contains_key(child, forbidden_key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, forbidden_key) for child in value)
    return False


def _select_reports(payload: dict[str, Any], corpus_dir: Path) -> list[dict[str, Any]]:
    reports = payload.get("reports", [])
    if not isinstance(reports, list):
        raise ValueError("analysis payload does not contain a reports list")

    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in SELECTION}
    for report in reports:
        if not isinstance(report, dict):
            continue
        severity = str(report.get("max_severity", ""))
        if severity not in grouped:
            continue
        report = dict(report)
        report["_relative_path"] = _relative_source_path(report, corpus_dir)
        grouped[severity].append(report)

    selected: list[dict[str, Any]] = []
    for severity, count in SELECTION.items():
        ordered = sorted(grouped[severity], key=lambda item: item["_relative_path"])
        if len(ordered) < count:
            raise ValueError(
                f"not enough {severity} workflows: expected {count}, got {len(ordered)}"
            )
        selected.extend(ordered[:count])
    return selected


def _validate_one(
    report: dict[str, Any],
    *,
    corpus_dir: Path,
    source_repo: str,
    source_commit: str,
) -> dict[str, Any]:
    relative_path = str(report["_relative_path"])
    workflow_path = corpus_dir / relative_path
    workflow = _read_untrusted_json(
        workflow_path,
        max_bytes=DEFAULT_MAX_WORKFLOW_BYTES,
        label="workflow",
    )
    raw = workflow_path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()

    analyzed_sha = str(report.get("sha256", ""))
    if analyzed_sha and analyzed_sha != sha256:
        raise AssertionError(f"SHA mismatch for {relative_path}")

    first = compile_knowledge_item(
        workflow,
        report,
        source_repo=source_repo,
        source_commit=source_commit,
        source_path=relative_path,
        source_sha256=sha256,
    )
    second = compile_knowledge_item(
        workflow,
        report,
        source_repo=source_repo,
        source_commit=source_commit,
        source_path=relative_path,
        source_sha256=sha256,
    )
    if first != second:
        raise AssertionError(f"non-deterministic compilation for {relative_path}")

    severity = str(report.get("max_severity"))
    role = first["admission"]["knowledge_role"]

    assert first["source_content_trust"] == "UNTRUSTED_SOURCE_DATA"
    assert first["provenance"]["source_repo"] == source_repo
    assert first["provenance"]["source_commit"] == source_commit
    assert first["provenance"]["source_path"] == relative_path
    assert first["provenance"]["sha256"] == sha256
    assert role == EXPECTED_ROLE[severity]
    assert first["admission"]["implementation_reference_allowed"] is False
    assert first["admission"]["vorquel_validated"] is False
    assert not _contains_key(first, "evidence")

    for snippet in first["executable_snippets_untrusted"]:
        assert snippet["content_persisted"] is False
        assert "content" not in snippet
        assert "code" not in snippet
        assert "command" not in snippet

    serialized = json.dumps(first, ensure_ascii=False, sort_keys=True)
    for credential_value in _source_credential_strings(workflow):
        assert credential_value not in serialized
    for executable_value in _source_executable_strings(workflow):
        assert executable_value not in serialized

    return {
        "source_path": relative_path,
        "severity": severity,
        "risk_decision": first["admission"]["risk_decision"],
        "knowledge_role": role,
        "node_count": first["workflow"]["node_count"],
        "untrusted_text_items": len(first["untrusted_text"]),
        "executable_metadata_items": len(first["executable_snippets_untrusted"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a stratified real-corpus compiler eval.")
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    corpus_dir = args.corpus_dir.resolve()
    analysis = _read_untrusted_json(
        args.analysis,
        max_bytes=50 * 1024 * 1024,
        label="analysis",
    )
    selected = _select_reports(analysis, corpus_dir)

    results = [
        _validate_one(
            report,
            corpus_dir=corpus_dir,
            source_repo=args.source_repo,
            source_commit=args.source_commit,
        )
        for report in selected
    ]

    severity_counts = Counter(item["severity"] for item in results)
    role_counts = Counter(item["knowledge_role"] for item in results)

    output = {
        "eval_version": "0.1",
        "sample_size": len(results),
        "severity_counts": dict(sorted(severity_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "selected": results,
        "all_invariants_passed": True,
        "source_execution_performed": False,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
