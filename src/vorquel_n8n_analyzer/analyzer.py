from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import Finding, WorkflowReport
from .rules import analyze_node, analyze_workflow_level

DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024


def _trigger_types(nodes: list[dict[str, Any]]) -> list[str]:
    triggers: list[str] = []
    for node in nodes:
        node_type = str(node.get("type", ""))
        lowered = node_type.lower()
        if "trigger" in lowered or lowered.endswith(".cron") or lowered.endswith(".scheduletrigger"):
            triggers.append(node_type)
    return sorted(set(triggers))


def analyze_workflow(
    workflow: dict[str, Any], *, source_path: str = "<memory>", sha256: str = ""
) -> WorkflowReport:
    nodes_raw = workflow.get("nodes", [])
    if not isinstance(nodes_raw, list):
        return WorkflowReport(
            source_path=source_path,
            sha256=sha256,
            workflow_name=str(workflow.get("name")) if workflow.get("name") else None,
            parse_error="Invalid n8n workflow: 'nodes' must be a list.",
        ).finalize()

    nodes = [node for node in nodes_raw if isinstance(node, dict)]
    node_types = Counter(str(node.get("type", "<missing>")) for node in nodes)
    findings: list[Finding] = []
    for node in nodes:
        findings.extend(analyze_node(node))
    findings.extend(analyze_workflow_level(workflow))

    report = WorkflowReport(
        source_path=source_path,
        sha256=sha256,
        workflow_name=str(workflow.get("name")) if workflow.get("name") else None,
        node_count=len(nodes),
        node_types=dict(sorted(node_types.items())),
        trigger_types=_trigger_types(nodes),
        findings=findings,
    )
    return report.finalize()


def analyze_file(path: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> WorkflowReport:
    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        return WorkflowReport(
            source_path=str(file_path),
            sha256="",
            workflow_name=None,
            parse_error=f"Unable to read file: {exc.__class__.__name__}",
        ).finalize()

    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > max_file_bytes:
        return WorkflowReport(
            source_path=str(file_path),
            sha256=digest,
            workflow_name=None,
            parse_error=f"File exceeds configured size limit ({max_file_bytes} bytes).",
        ).finalize()

    try:
        workflow = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return WorkflowReport(
            source_path=str(file_path),
            sha256=digest,
            workflow_name=None,
            parse_error=f"Invalid JSON: {exc.__class__.__name__}",
        ).finalize()

    if not isinstance(workflow, dict):
        return WorkflowReport(
            source_path=str(file_path),
            sha256=digest,
            workflow_name=None,
            parse_error="Invalid n8n workflow: top-level JSON must be an object.",
        ).finalize()

    return analyze_workflow(workflow, source_path=str(file_path), sha256=digest)
