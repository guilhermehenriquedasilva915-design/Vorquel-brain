from __future__ import annotations

from pathlib import Path
from typing import Any

from vorquel_n8n_analyzer.analyzer import analyze_file
from vorquel_n8n_knowledge_compiler.compiler import compile_knowledge_item

from .common import (
    MAX_MANIFEST_ITEMS,
    MAX_WORKFLOW_BYTES,
    ControlledIngestionError,
    read_json_object,
    safe_relative_path,
    sha256_bytes,
    controlled_structure_item,
    workflow_has_credentials,
)


def _report_payload(report) -> dict[str, Any]:
    return report.to_dict()


def build_manifest(
    corpus_root: Path,
    *,
    source_repo: str,
    source_commit: str,
    analyzer_version: str,
    max_items: int = MAX_MANIFEST_ITEMS,
) -> dict[str, Any]:
    if max_items < 1 or max_items > MAX_MANIFEST_ITEMS:
        raise ControlledIngestionError(
            f"max_items must be between 1 and {MAX_MANIFEST_ITEMS}"
        )
    if not corpus_root.exists() or not corpus_root.is_dir():
        raise ControlledIngestionError("corpus root must be an existing directory")
    if corpus_root.is_symlink():
        raise ControlledIngestionError("corpus root may not be a symlink")

    selected: list[dict[str, Any]] = []

    for path in sorted(corpus_root.rglob("*.json")):
        if len(selected) >= max_items:
            break
        if path.is_symlink():
            continue

        relative = safe_relative_path(corpus_root, path)
        report = analyze_file(path, max_file_bytes=MAX_WORKFLOW_BYTES)
        report_payload = _report_payload(report)
        if report.parse_error is not None:
            continue
        if report.risk_decision != "SAFE_FOR_LEARNING":
            continue
        raw, workflow = read_json_object(
            path,
            max_bytes=MAX_WORKFLOW_BYTES,
            label=f"workflow:{relative}",
        )
        if workflow_has_credentials(workflow):
            continue

        digest = sha256_bytes(raw)
        if digest != report.sha256:
            raise ControlledIngestionError(
                f"workflow:{relative}: analyzer/source SHA-256 mismatch"
            )

        item = compile_knowledge_item(
            workflow,
            report_payload,
            source_repo=source_repo,
            source_commit=source_commit,
            source_path=relative,
            source_sha256=digest,
        )
        if not controlled_structure_item(item):
            continue

        selected.append(
            {
                "source_path": relative,
                "sha256": digest,
                "risk_decision": item["admission"]["risk_decision"],
                "knowledge_role": item["admission"]["knowledge_role"],
                "node_count": item["workflow"]["node_count"],
            }
        )

    if len(selected) != max_items:
        raise ControlledIngestionError(
            f"controlled-structure planner found {len(selected)} item(s); expected {max_items}"
        )

    return {
        "manifest_version": "0.1",
        "source_repo": source_repo,
        "source_commit": source_commit,
        "analyzer_version": analyzer_version,
        "selection_profile": "CONTROLLED_STRUCTURE_V0_1",
        "items": selected,
    }
