"""JSON.

Addressed by JSON path. The one thing this adapter refuses to do is read an
n8n workflow: a workflow that arrives as "just a JSON file" must still go
through the Analyzer and the Compiler, because they are what classify embedded
code as untrusted and decide the admission role. Letting it in through the
generic path would be a bypass of the entire admission policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, LearnError, SourceRef, sha256_bytes
from ..scope_util import resolve_scope

# Deep enough to address a meaningful field, shallow enough that a hostile file
# cannot turn one document into tens of thousands of candidates.
MAX_DEPTH = 4
MAX_UNITS = 500


def looks_like_n8n_workflow(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False
    if "connections" in payload:
        return True
    return any(
        isinstance(node, dict) and "type" in node and "parameters" in node for node in nodes
    )


def _walk(value: Any, path: str, depth: int, out: list[tuple[str, str]]) -> None:
    if len(out) >= MAX_UNITS:
        return
    if isinstance(value, dict):
        if depth >= MAX_DEPTH:
            out.append((path, json.dumps(value, ensure_ascii=False, sort_keys=True)))
            return
        for key in sorted(value):
            _walk(value[key], f"{path}.{key}" if path else str(key), depth + 1, out)
    elif isinstance(value, list):
        if depth >= MAX_DEPTH:
            out.append((path, json.dumps(value, ensure_ascii=False)))
            return
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", depth + 1, out)
    else:
        out.append((path, "" if value is None else str(value)))


def learn_json(
    path: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
    logical_key: str | None = None,
) -> LearnBatch:
    file_path = Path(path)
    payload_bytes = file_path.read_bytes()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LearnError(f"JSON invalido: {type(exc).__name__}") from exc

    if looks_like_n8n_workflow(payload):
        raise LearnError(
            "este JSON e um workflow n8n. Use o adaptador de workflow "
            "(Analyzer + Compiler); a leitura crua ignoraria a politica de admissao."
        )

    source = SourceRef(
        source_kind="JSON",
        content_sha256=sha256_bytes(payload_bytes),
        byte_size=len(payload_bytes),
        detected_mime="application/json",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        logical_key=logical_key or file_path.name,
        external_metadata={"filename": file_path.name},
    )

    flattened: list[tuple[str, str]] = []
    _walk(payload, "", 0, flattened)

    units = [
        RawUnit(
            title=json_path or "(raiz)",
            text=f"{json_path}: {text}" if json_path else text,
            locator_kind="GENERIC",
            locator={"path": json_path[:200]},
        )
        for json_path, text in flattened
    ]
    return to_batch(source, units, data_classification)
