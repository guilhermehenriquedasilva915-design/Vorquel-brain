from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from psycopg import Connection
from vorquel_n8n_analyzer.analyzer import analyze_file
from vorquel_n8n_knowledge_compiler.compiler import compile_knowledge_item
from vorquel_n8n_knowledge_writer.validation import prepare_records
from vorquel_n8n_knowledge_writer.writer import WriteResult, write_prepared_records

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

_GIT_HASH = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ALLOWED_MANIFEST = {
    "manifest_version",
    "source_repo",
    "source_commit",
    "analyzer_version",
    "selection_profile",
    "items",
}
_ALLOWED_ITEM = {
    "source_path",
    "sha256",
    "risk_decision",
    "knowledge_role",
    "node_count",
}


def _exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = set(value) - allowed
    missing = allowed - set(value)
    if extras:
        raise ControlledIngestionError(
            f"{label}: unexpected field(s): {', '.join(sorted(extras))}"
        )
    if missing:
        raise ControlledIngestionError(
            f"{label}: missing field(s): {', '.join(sorted(missing))}"
        )


def load_manifest(path: Path) -> dict[str, Any]:
    _, payload = read_json_object(
        path,
        max_bytes=256 * 1024,
        label="manifest",
    )
    _exact_keys(payload, _ALLOWED_MANIFEST, "manifest")

    if payload["manifest_version"] != "0.1":
        raise ControlledIngestionError("manifest: unsupported version")
    if payload["selection_profile"] != "CONTROLLED_STRUCTURE_V0_1":
        raise ControlledIngestionError("manifest: unsupported selection profile")

    source_repo = payload["source_repo"]
    source_commit = payload["source_commit"]
    analyzer_version = payload["analyzer_version"]
    if not isinstance(source_repo, str) or not (1 <= len(source_repo) <= 512):
        raise ControlledIngestionError("manifest.source_repo: invalid")
    if not isinstance(source_commit, str) or not _GIT_HASH.fullmatch(source_commit):
        raise ControlledIngestionError("manifest.source_commit: invalid git hash")
    if not isinstance(analyzer_version, str) or not (1 <= len(analyzer_version) <= 128):
        raise ControlledIngestionError("manifest.analyzer_version: invalid")

    items = payload["items"]
    if not isinstance(items, list) or not (1 <= len(items) <= MAX_MANIFEST_ITEMS):
        raise ControlledIngestionError(
            f"manifest.items: must contain 1..{MAX_MANIFEST_ITEMS} items"
        )

    seen_paths: set[str] = set()
    for index, item in enumerate(items):
        label = f"manifest.items[{index}]"
        if not isinstance(item, dict):
            raise ControlledIngestionError(f"{label}: must be an object")
        _exact_keys(item, _ALLOWED_ITEM, label)

        source_path = item["source_path"]
        if not isinstance(source_path, str) or not source_path:
            raise ControlledIngestionError(f"{label}.source_path: invalid")
        pure = Path(source_path)
        if pure.is_absolute() or ".." in pure.parts:
            raise ControlledIngestionError(f"{label}.source_path: unsafe path")
        if source_path in seen_paths:
            raise ControlledIngestionError(f"{label}.source_path: duplicate")
        seen_paths.add(source_path)

        sha256 = item["sha256"]
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise ControlledIngestionError(f"{label}.sha256: invalid")
        if item["risk_decision"] != "SAFE_FOR_LEARNING":
            raise ControlledIngestionError(f"{label}.risk_decision: must be SAFE_FOR_LEARNING")
        if item["knowledge_role"] not in {
            "REFERENCE_PATTERN",
            "STRUCTURE_REFERENCE_RESTRICTED",
        }:
            raise ControlledIngestionError(
                f"{label}.knowledge_role: unsupported for controlled ingestion"
            )
        node_count = item["node_count"]
        if isinstance(node_count, bool) or not isinstance(node_count, int) or node_count <= 0:
            raise ControlledIngestionError(f"{label}.node_count: must be > 0")

    return payload


def _rebuild_item(
    *,
    corpus_root: Path,
    manifest: dict[str, Any],
    manifest_item: dict[str, Any],
) -> dict[str, Any]:
    path = corpus_root / manifest_item["source_path"]
    relative = safe_relative_path(corpus_root, path)
    if relative != manifest_item["source_path"]:
        raise ControlledIngestionError("manifest/source path normalization mismatch")

    report = analyze_file(path, max_file_bytes=MAX_WORKFLOW_BYTES)
    if report.parse_error is not None:
        raise ControlledIngestionError(f"{relative}: analyzer parse error")
    if report.risk_decision != "SAFE_FOR_LEARNING":
        raise ControlledIngestionError(
            f"{relative}: no longer satisfies controlled analysis"
        )

    raw, workflow = read_json_object(
        path,
        max_bytes=MAX_WORKFLOW_BYTES,
        label=f"workflow:{relative}",
    )
    if workflow_has_credentials(workflow):
        raise ControlledIngestionError(f"{relative}: credentials are not allowed")

    digest = sha256_bytes(raw)
    if digest != manifest_item["sha256"] or digest != report.sha256:
        raise ControlledIngestionError(f"{relative}: SHA-256 mismatch")

    item = compile_knowledge_item(
        workflow,
        report.to_dict(),
        source_repo=manifest["source_repo"],
        source_commit=manifest["source_commit"],
        source_path=relative,
        source_sha256=digest,
    )
    if not controlled_structure_item(item):
        raise ControlledIngestionError(f"{relative}: compiled item is outside controlled structure policy")

    if item["workflow"]["node_count"] != manifest_item["node_count"]:
        raise ControlledIngestionError(f"{relative}: node_count drift")
    if item["admission"]["risk_decision"] != manifest_item["risk_decision"]:
        raise ControlledIngestionError(f"{relative}: risk decision drift")
    if item["admission"]["knowledge_role"] != manifest_item["knowledge_role"]:
        raise ControlledIngestionError(f"{relative}: knowledge role drift")

    prepare_records(item, analyzer_version=manifest["analyzer_version"])
    return item


def ingest_manifest(
    corpus_root: Path,
    manifest: dict[str, Any],
    *,
    connection: Connection[Any] | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    if not corpus_root.exists() or not corpus_root.is_dir():
        raise ControlledIngestionError("corpus root must be an existing directory")
    if corpus_root.is_symlink():
        raise ControlledIngestionError("corpus root may not be a symlink")

    rebuilt: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for manifest_item in manifest["items"]:
        item = _rebuild_item(
            corpus_root=corpus_root,
            manifest=manifest,
            manifest_item=manifest_item,
        )
        rebuilt.append((manifest_item, item))

    if not persist:
        return {
            "status": "VALIDATED",
            "dry_run": True,
            "item_count": len(rebuilt),
            "items": [
                {
                    "source_path": manifest_item["source_path"],
                    "sha256": manifest_item["sha256"],
                    "risk_decision": manifest_item["risk_decision"],
                    "knowledge_role": manifest_item["knowledge_role"],
                }
                for manifest_item, _ in rebuilt
            ],
        }

    if connection is None:
        raise ControlledIngestionError("persistence requires a database connection")

    results: list[tuple[dict[str, Any], WriteResult]] = []
    with connection.transaction():
        for manifest_item, item in rebuilt:
            records = prepare_records(
                item,
                analyzer_version=manifest["analyzer_version"],
            )
            result = write_prepared_records(connection, records)
            results.append((manifest_item, result))

    return {
        "status": "PERSISTED",
        "dry_run": False,
        "item_count": len(results),
        "items": [
            {
                "source_path": manifest_item["source_path"],
                "sha256": manifest_item["sha256"],
                "created": {
                    "source": result.source_created,
                    "analysis": result.analysis_created,
                    "knowledge": result.knowledge_created,
                },
            }
            for manifest_item, result in results
        ],
    }
