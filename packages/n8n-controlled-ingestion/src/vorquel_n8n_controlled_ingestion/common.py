from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_WORKFLOW_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_ITEMS = 4


class ControlledIngestionError(ValueError):
    """Raised when the controlled ingestion contract is violated."""


def read_json_object(path: Path, *, max_bytes: int, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink():
        raise ControlledIngestionError(f"{label}: symlink input is not allowed")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ControlledIngestionError(
            f"{label}: unable to stat input ({exc.__class__.__name__})"
        ) from exc
    if size > max_bytes:
        raise ControlledIngestionError(
            f"{label}: exceeds configured size limit ({max_bytes} bytes)"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ControlledIngestionError(
            f"{label}: unable to read input ({exc.__class__.__name__})"
        ) from exc
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ControlledIngestionError(f"{label}: invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ControlledIngestionError(f"{label}: JSON must be an object")
    return raw, payload


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative_path(root: Path, candidate: Path) -> str:
    root_resolved = root.resolve()
    if candidate.is_symlink():
        raise ControlledIngestionError("workflow path: symlink is not allowed")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ControlledIngestionError(
            f"workflow path: unable to resolve ({exc.__class__.__name__})"
        ) from exc
    try:
        relative = resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ControlledIngestionError("workflow path escapes corpus root") from exc
    return relative.as_posix()


def workflow_has_credentials(workflow: dict[str, Any]) -> bool:
    nodes = workflow.get("nodes", [])
    if not isinstance(nodes, list):
        return True
    for node in nodes:
        if not isinstance(node, dict):
            continue
        credentials = node.get("credentials")
        if isinstance(credentials, dict) and credentials:
            return True
    return False


def controlled_structure_item(item: dict[str, Any]) -> bool:
    admission = item.get("admission")
    workflow = item.get("workflow")
    if not isinstance(admission, dict) or not isinstance(workflow, dict):
        return False
    if admission.get("risk_decision") != "SAFE_FOR_LEARNING":
        return False
    if admission.get("knowledge_role") not in {
        "REFERENCE_PATTERN",
        "STRUCTURE_REFERENCE_RESTRICTED",
    }:
        return False
    findings = item.get("security_findings")
    if not isinstance(findings, list):
        return False
    allowed_rules = {"NETWORK_REQUEST"}
    for finding in findings:
        if not isinstance(finding, dict):
            return False
        if finding.get("rule_id") not in allowed_rules:
            return False
        if finding.get("severity") != "MEDIUM":
            return False
    if item.get("executable_snippets_untrusted") != []:
        return False
    if not isinstance(workflow.get("node_count"), int) or workflow["node_count"] <= 0:
        return False
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            return False
        credential_types = node.get("credential_types")
        if credential_types not in ([], None):
            return False
    return True
