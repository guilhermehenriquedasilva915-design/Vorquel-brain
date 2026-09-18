from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vorquel_n8n_analyzer import analyze_workflow
from vorquel_n8n_knowledge_compiler import compile_knowledge_item
from vorquel_n8n_knowledge_writer.validation import PreparedRecords, prepare_records

MANIFEST_VERSION = "0.1"
POLICY = "STRICT_REFERENCE_V01"
MAX_ITEMS = 4
MAX_FILE_BYTES = 5 * 1024 * 1024

_GIT_HASH = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ControlledIngestError(ValueError):
    """Raised when planning or ingestion violates the controlled-ingest contract."""


@dataclass(frozen=True)
class CompiledManifestItem:
    source_path: str
    sha256: str
    risk_decision: str
    max_severity: str
    knowledge_role: str
    node_count: int
    records: PreparedRecords


def _fail(message: str) -> None:
    raise ControlledIngestError(message)


def _validate_source_identity(source_repo: str, source_commit: str) -> None:
    if not isinstance(source_repo, str) or not (1 <= len(source_repo) <= 512):
        _fail("source_repo must be a non-empty string up to 512 characters")
    if not isinstance(source_commit, str) or not _GIT_HASH.fullmatch(source_commit):
        _fail("source_commit must be a lowercase 40- or 64-character git hash")


def _safe_path(corpus_root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        _fail("manifest source_path must be a non-empty string")
    if len(relative_path) > 2048:
        _fail("manifest source_path exceeds 2048 characters")

    rel = Path(relative_path)
    if rel.is_absolute():
        _fail("manifest source_path must be relative")
    if any(part in {"..", ""} for part in rel.parts):
        _fail("manifest source_path contains unsafe path traversal")

    root = corpus_root.resolve()
    candidate = root / rel
    if candidate.is_symlink():
        _fail(f"symlink input is not allowed: {relative_path}")

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ControlledIngestError(
            f"unable to resolve manifest input: {relative_path} ({exc.__class__.__name__})"
        ) from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ControlledIngestError(
            f"manifest input escapes corpus root: {relative_path}"
        ) from exc

    if not resolved.is_file():
        _fail(f"manifest input is not a file: {relative_path}")
    if resolved.suffix.lower() != ".json":
        _fail(f"manifest input must be JSON: {relative_path}")
    return resolved


def _read_workflow(path: Path) -> tuple[dict[str, Any], str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ControlledIngestError(
            f"unable to stat workflow ({exc.__class__.__name__})"
        ) from exc

    if size > MAX_FILE_BYTES:
        _fail(f"workflow exceeds {MAX_FILE_BYTES} byte limit")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ControlledIngestError(
            f"unable to read workflow ({exc.__class__.__name__})"
        ) from exc

    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ControlledIngestError("workflow is not valid JSON") from exc

    if not isinstance(payload, dict):
        _fail("workflow JSON must be an object")
    return payload, digest


def _credential_type_count(item: dict[str, Any]) -> int:
    nodes = item.get("workflow", {}).get("nodes", [])
    count = 0
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            credentials = node.get("credential_types", [])
            if isinstance(credentials, list):
                count += len(credentials)
    return count


def _strict_reason(item: dict[str, Any]) -> str | None:
    admission = item.get("admission", {})
    if admission.get("risk_decision") != "SAFE_FOR_LEARNING":
        return "risk_decision is not SAFE_FOR_LEARNING"
    if admission.get("max_severity") != "INFO":
        return "max_severity is not INFO"
    if admission.get("knowledge_role") != "REFERENCE_PATTERN":
        return "knowledge_role is not REFERENCE_PATTERN"
    if item.get("security_findings"):
        return "security findings are present"
    if item.get("untrusted_text"):
        return "untrusted text is present"
    if item.get("executable_snippets_untrusted"):
        return "executable metadata is present"
    if _credential_type_count(item):
        return "credential references are present"

    workflow = item.get("workflow", {})
    node_count = workflow.get("node_count", 0)
    if isinstance(node_count, bool) or not isinstance(node_count, int) or node_count <= 0:
        return "workflow has no nodes"
    return None


def _compile_path(
    corpus_root: Path,
    relative_path: str,
    *,
    source_repo: str,
    source_commit: str,
    analyzer_version: str,
) -> CompiledManifestItem:
    path = _safe_path(corpus_root, relative_path)
    workflow, digest = _read_workflow(path)

    report = analyze_workflow(
        workflow,
        source_path=relative_path,
        sha256=digest,
    ).to_dict()
    if report.get("parse_error"):
        _fail(f"analyzer rejected workflow: {relative_path}")

    item = compile_knowledge_item(
        workflow,
        report,
        source_repo=source_repo,
        source_commit=source_commit,
        source_path=relative_path,
        source_sha256=digest,
    )
    reason = _strict_reason(item)
    if reason is not None:
        _fail(f"workflow does not satisfy {POLICY}: {relative_path}: {reason}")

    records = prepare_records(item, analyzer_version=analyzer_version)
    admission = item["admission"]
    return CompiledManifestItem(
        source_path=relative_path,
        sha256=digest,
        risk_decision=str(admission["risk_decision"]),
        max_severity=str(admission["max_severity"]),
        knowledge_role=str(admission["knowledge_role"]),
        node_count=int(item["workflow"]["node_count"]),
        records=records,
    )


def plan_manifest(
    corpus_root: str | Path,
    *,
    source_repo: str,
    source_commit: str,
    analyzer_version: str,
    count: int,
) -> dict[str, Any]:
    _validate_source_identity(source_repo, source_commit)
    if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= MAX_ITEMS):
        _fail(f"count must be between 1 and {MAX_ITEMS}")

    root = Path(corpus_root).resolve()
    if not root.is_dir():
        _fail("corpus root must be a directory")

    selected: list[CompiledManifestItem] = []
    candidates = sorted(
        path for path in root.rglob("*.json")
        if path.is_file() and not path.is_symlink()
    )

    for path in candidates:
        try:
            relative_path = path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            compiled = _compile_path(
                root,
                relative_path,
                source_repo=source_repo,
                source_commit=source_commit,
                analyzer_version=analyzer_version,
            )
        except ControlledIngestError:
            continue
        selected.append(compiled)
        if len(selected) == count:
            break

    if len(selected) != count:
        _fail(f"only {len(selected)} workflows satisfied {POLICY}; {count} requested")

    return {
        "manifest_version": MANIFEST_VERSION,
        "policy": POLICY,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "analyzer_version": analyzer_version,
        "items": [
            {
                "source_path": item.source_path,
                "sha256": item.sha256,
                "risk_decision": item.risk_decision,
                "max_severity": item.max_severity,
                "knowledge_role": item.knowledge_role,
                "node_count": item.node_count,
            }
            for item in selected
        ],
    }


def _load_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("manifest must be an object")

    allowed = {
        "manifest_version",
        "policy",
        "source_repo",
        "source_commit",
        "analyzer_version",
        "items",
    }
    extras = set(value) - allowed
    if extras:
        _fail(f"manifest has unexpected field(s): {', '.join(sorted(extras))}")

    if value.get("manifest_version") != MANIFEST_VERSION:
        _fail("unsupported manifest_version")
    if value.get("policy") != POLICY:
        _fail("unsupported manifest policy")

    source_repo = value.get("source_repo")
    source_commit = value.get("source_commit")
    _validate_source_identity(source_repo, source_commit)

    analyzer_version = value.get("analyzer_version")
    if not isinstance(analyzer_version, str) or not (1 <= len(analyzer_version) <= 128):
        _fail("manifest analyzer_version is invalid")

    items = value.get("items")
    if not isinstance(items, list) or not (1 <= len(items) <= MAX_ITEMS):
        _fail(f"manifest must contain between 1 and {MAX_ITEMS} items")

    return {
        "manifest_version": MANIFEST_VERSION,
        "policy": POLICY,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "analyzer_version": analyzer_version,
        "items": items,
    }


def compile_manifest_items(
    corpus_root: str | Path,
    manifest: Any,
) -> list[CompiledManifestItem]:
    clean = _load_manifest(manifest)
    root = Path(corpus_root).resolve()
    if not root.is_dir():
        _fail("corpus root must be a directory")

    seen_paths: set[str] = set()
    compiled_items: list[CompiledManifestItem] = []

    for index, raw_item in enumerate(clean["items"]):
        if not isinstance(raw_item, dict):
            _fail(f"manifest items[{index}] must be an object")
        allowed = {
            "source_path",
            "sha256",
            "risk_decision",
            "max_severity",
            "knowledge_role",
            "node_count",
        }
        extras = set(raw_item) - allowed
        if extras:
            _fail(f"manifest items[{index}] has unexpected fields")

        source_path = raw_item.get("source_path")
        if not isinstance(source_path, str):
            _fail(f"manifest items[{index}].source_path must be a string")
        if source_path in seen_paths:
            _fail(f"manifest contains duplicate source_path: {source_path}")
        seen_paths.add(source_path)

        expected_sha = raw_item.get("sha256")
        if not isinstance(expected_sha, str) or not _SHA256.fullmatch(expected_sha):
            _fail(f"manifest items[{index}].sha256 is invalid")

        compiled = _compile_path(
            root,
            source_path,
            source_repo=clean["source_repo"],
            source_commit=clean["source_commit"],
            analyzer_version=clean["analyzer_version"],
        )

        expected = {
            "sha256": expected_sha,
            "risk_decision": raw_item.get("risk_decision"),
            "max_severity": raw_item.get("max_severity"),
            "knowledge_role": raw_item.get("knowledge_role"),
            "node_count": raw_item.get("node_count"),
        }
        observed = {
            "sha256": compiled.sha256,
            "risk_decision": compiled.risk_decision,
            "max_severity": compiled.max_severity,
            "knowledge_role": compiled.knowledge_role,
            "node_count": compiled.node_count,
        }
        if observed != expected:
            _fail(f"manifest drift detected for {source_path}")

        compiled_items.append(compiled)

    return compiled_items
