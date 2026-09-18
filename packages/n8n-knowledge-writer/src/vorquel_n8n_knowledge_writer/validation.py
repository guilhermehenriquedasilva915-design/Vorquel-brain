from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_HASH = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/@-]{1,128}$")

_ALLOWED_TOP_LEVEL = {
    "schema_version",
    "kind",
    "source_content_trust",
    "provenance",
    "workflow",
    "admission",
    "security_findings",
    "untrusted_text",
    "executable_snippets_untrusted",
}
_ALLOWED_PROVENANCE = {"source_repo", "source_commit", "source_path", "sha256"}
_ALLOWED_WORKFLOW = {
    "name_untrusted",
    "node_count",
    "node_types",
    "trigger_types",
    "integrations",
    "nodes",
    "edges",
}
_ALLOWED_NODE = {
    "name_untrusted",
    "type",
    "type_version",
    "resource",
    "operation",
    "credential_types",
}
_ALLOWED_EDGE = {
    "source_name_untrusted",
    "target_name_untrusted",
    "channel",
    "source_output_index",
    "target_input_index",
}
_ALLOWED_ADMISSION = {
    "source_stage",
    "analysis_stage",
    "risk_decision",
    "max_severity",
    "knowledge_role",
    "learning_scope",
    "structure_reference_allowed",
    "implementation_reference_allowed",
    "vorquel_validated",
}
_ALLOWED_FINDING = {"rule_id", "severity", "node_name", "node_type", "json_path"}
_ALLOWED_UNTRUSTED_TEXT = {
    "kind",
    "node_name",
    "node_type",
    "json_path",
    "sha256",
    "char_count",
    "preview",
}
_ALLOWED_EXECUTABLE = {
    "kind",
    "node_name",
    "node_type",
    "json_path",
    "reason",
    "language",
    "sha256",
    "char_count",
    "content_persisted",
}

_EXPECTED_ROLE = {
    ("SAFE_FOR_LEARNING", "INFO"): ("REFERENCE_PATTERN", "structure_and_metadata"),
    ("SAFE_FOR_LEARNING", "LOW"): ("REFERENCE_PATTERN", "structure_and_metadata"),
    ("SAFE_FOR_LEARNING", "MEDIUM"): (
        "STRUCTURE_REFERENCE_RESTRICTED",
        "structure_only",
    ),
    ("REVIEW_REQUIRED", "HIGH"): ("QUARANTINED_REFERENCE", "review_only"),
    ("BLOCKED", "CRITICAL"): ("SECURITY_EXAMPLE", "security_only"),
}


class KnowledgeItemValidationError(ValueError):
    """Raised when a knowledge item violates the persistence contract."""


@dataclass(frozen=True)
class PreparedRecords:
    source: dict[str, Any]
    analysis: dict[str, Any]
    knowledge: dict[str, Any]


def _fail(path: str, message: str) -> None:
    raise KnowledgeItemValidationError(f"{path}: {message}")


def _exact_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    extras = set(value) - allowed
    if extras:
        _fail(path, f"unexpected field(s): {', '.join(sorted(extras))}")


def _dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "must be an array")
    return value


def _string(value: Any, path: str, *, max_len: int, nonempty: bool = True) -> str:
    if not isinstance(value, str):
        _fail(path, "must be a string")
    if nonempty and not value:
        _fail(path, "must not be empty")
    if len(value) > max_len:
        _fail(path, f"must be at most {max_len} characters")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")
    return value


def _int(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer")
    if value < minimum:
        _fail(path, f"must be >= {minimum}")
    return value


def _nullable_string(value: Any, path: str, *, max_len: int = 512) -> str | None:
    if value is None:
        return None
    return _string(value, path, max_len=max_len, nonempty=False)


def _safe_scalar(value: Any, path: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    _fail(path, "must be a safe metadata scalar")


def _contains_key(value: Any, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        if set(value) & forbidden:
            return True
        return any(_contains_key(child, forbidden) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


def _validate_provenance(value: Any) -> dict[str, str]:
    provenance = _dict(value, "provenance")
    _exact_keys(provenance, _ALLOWED_PROVENANCE, "provenance")

    source_repo = _string(
        provenance.get("source_repo"),
        "provenance.source_repo",
        max_len=512,
    )
    source_commit = _string(
        provenance.get("source_commit"),
        "provenance.source_commit",
        max_len=64,
    )
    source_path = _string(
        provenance.get("source_path"),
        "provenance.source_path",
        max_len=2048,
    )
    sha256 = _string(provenance.get("sha256"), "provenance.sha256", max_len=64)

    if not _GIT_HASH.fullmatch(source_commit):
        _fail("provenance.source_commit", "must be a 40- or 64-character lowercase git hash")
    if not _SHA256.fullmatch(sha256):
        _fail("provenance.sha256", "must be a lowercase SHA-256 hex digest")

    return {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "source_path": source_path,
        "sha256": sha256,
    }


def _validate_workflow(value: Any) -> dict[str, Any]:
    workflow = _dict(value, "workflow")
    _exact_keys(workflow, _ALLOWED_WORKFLOW, "workflow")

    name = _string(
        workflow.get("name_untrusted"),
        "workflow.name_untrusted",
        max_len=256,
        nonempty=False,
    )
    node_count = _int(workflow.get("node_count"), "workflow.node_count")

    node_types = _dict(workflow.get("node_types"), "workflow.node_types")
    clean_node_types: dict[str, int] = {}
    for key, count in node_types.items():
        node_type = _string(key, "workflow.node_types.<key>", max_len=256)
        clean_node_types[node_type] = _int(
            count,
            f"workflow.node_types.{node_type}",
            minimum=0,
        )

    trigger_types = [
        _string(item, "workflow.trigger_types[]", max_len=256)
        for item in _list(workflow.get("trigger_types"), "workflow.trigger_types")
    ]
    integrations = [
        _string(item, "workflow.integrations[]", max_len=256)
        for item in _list(workflow.get("integrations"), "workflow.integrations")
    ]

    nodes: list[dict[str, Any]] = []
    for index, raw_node in enumerate(_list(workflow.get("nodes"), "workflow.nodes")):
        path = f"workflow.nodes[{index}]"
        node = _dict(raw_node, path)
        _exact_keys(node, _ALLOWED_NODE, path)
        credential_types = [
            _string(item, f"{path}.credential_types[]", max_len=128)
            for item in _list(node.get("credential_types"), f"{path}.credential_types")
        ]
        nodes.append(
            {
                "name_untrusted": _string(
                    node.get("name_untrusted"),
                    f"{path}.name_untrusted",
                    max_len=256,
                    nonempty=False,
                ),
                "type": _string(node.get("type"), f"{path}.type", max_len=256),
                "type_version": _safe_scalar(
                    node.get("type_version"),
                    f"{path}.type_version",
                ),
                "resource": _safe_scalar(node.get("resource"), f"{path}.resource"),
                "operation": _safe_scalar(node.get("operation"), f"{path}.operation"),
                "credential_types": sorted(credential_types),
            }
        )

    if node_count != len(nodes):
        _fail("workflow.node_count", "must equal the number of node records")

    edges: list[dict[str, Any]] = []
    for index, raw_edge in enumerate(_list(workflow.get("edges"), "workflow.edges")):
        path = f"workflow.edges[{index}]"
        edge = _dict(raw_edge, path)
        _exact_keys(edge, _ALLOWED_EDGE, path)
        edges.append(
            {
                "source_name_untrusted": _string(
                    edge.get("source_name_untrusted"),
                    f"{path}.source_name_untrusted",
                    max_len=256,
                    nonempty=False,
                ),
                "target_name_untrusted": _string(
                    edge.get("target_name_untrusted"),
                    f"{path}.target_name_untrusted",
                    max_len=256,
                    nonempty=False,
                ),
                "channel": _string(
                    edge.get("channel"),
                    f"{path}.channel",
                    max_len=256,
                    nonempty=False,
                ),
                "source_output_index": _int(
                    edge.get("source_output_index"),
                    f"{path}.source_output_index",
                ),
                "target_input_index": _int(
                    edge.get("target_input_index"),
                    f"{path}.target_input_index",
                ),
            }
        )

    return {
        "name_untrusted": name,
        "node_count": node_count,
        "node_types": dict(sorted(clean_node_types.items())),
        "trigger_types": sorted(set(trigger_types)),
        "integrations": sorted(set(integrations)),
        "nodes": nodes,
        "edges": edges,
    }


def _validate_findings(value: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(_list(value, "security_findings")):
        path = f"security_findings[{index}]"
        finding = _dict(raw, path)
        _exact_keys(finding, _ALLOWED_FINDING, path)
        findings.append(
            {
                "rule_id": _nullable_string(
                    finding.get("rule_id"), f"{path}.rule_id", max_len=128
                ),
                "severity": _nullable_string(
                    finding.get("severity"), f"{path}.severity", max_len=32
                ),
                "node_name": _nullable_string(
                    finding.get("node_name"), f"{path}.node_name", max_len=256
                ),
                "node_type": _nullable_string(
                    finding.get("node_type"), f"{path}.node_type", max_len=256
                ),
                "json_path": _nullable_string(
                    finding.get("json_path"), f"{path}.json_path", max_len=2048
                ),
            }
        )
    return findings


def _validate_untrusted_text(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(_list(value, "untrusted_text")):
        path = f"untrusted_text[{index}]"
        item = _dict(raw, path)
        _exact_keys(item, _ALLOWED_UNTRUSTED_TEXT, path)

        sha256 = _string(item.get("sha256"), f"{path}.sha256", max_len=64)
        if not _SHA256.fullmatch(sha256):
            _fail(f"{path}.sha256", "must be a lowercase SHA-256 hex digest")

        clean = {
            "kind": _string(item.get("kind"), f"{path}.kind", max_len=64),
            "node_name": _string(
                item.get("node_name"),
                f"{path}.node_name",
                max_len=256,
                nonempty=False,
            ),
            "node_type": _string(
                item.get("node_type"),
                f"{path}.node_type",
                max_len=256,
                nonempty=False,
            ),
            "json_path": _string(
                item.get("json_path"),
                f"{path}.json_path",
                max_len=2048,
            ),
            "sha256": sha256,
            "char_count": _int(item.get("char_count"), f"{path}.char_count"),
        }
        if "preview" in item:
            clean["preview"] = _string(
                item.get("preview"),
                f"{path}.preview",
                max_len=400,
                nonempty=False,
            )
        result.append(clean)
    return result


def _validate_executable(value: Any) -> list[dict[str, Any]]:
    if _contains_key(value, {"content", "code", "command"}):
        _fail(
            "executable_snippets_untrusted",
            "must not contain raw content, code, or command fields",
        )

    result: list[dict[str, Any]] = []
    for index, raw in enumerate(_list(value, "executable_snippets_untrusted")):
        path = f"executable_snippets_untrusted[{index}]"
        item = _dict(raw, path)
        _exact_keys(item, _ALLOWED_EXECUTABLE, path)

        sha256 = _string(item.get("sha256"), f"{path}.sha256", max_len=64)
        if not _SHA256.fullmatch(sha256):
            _fail(f"{path}.sha256", "must be a lowercase SHA-256 hex digest")

        content_persisted = _bool(
            item.get("content_persisted"),
            f"{path}.content_persisted",
        )
        if content_persisted:
            _fail(f"{path}.content_persisted", "must remain false in V0.1")

        result.append(
            {
                "kind": _string(item.get("kind"), f"{path}.kind", max_len=64),
                "node_name": _string(
                    item.get("node_name"),
                    f"{path}.node_name",
                    max_len=256,
                    nonempty=False,
                ),
                "node_type": _string(
                    item.get("node_type"),
                    f"{path}.node_type",
                    max_len=256,
                    nonempty=False,
                ),
                "json_path": _string(
                    item.get("json_path"),
                    f"{path}.json_path",
                    max_len=2048,
                ),
                "reason": _string(item.get("reason"), f"{path}.reason", max_len=128),
                "language": _string(
                    item.get("language"),
                    f"{path}.language",
                    max_len=128,
                ),
                "sha256": sha256,
                "char_count": _int(item.get("char_count"), f"{path}.char_count"),
                "content_persisted": False,
            }
        )
    return result


def _validate_admission(value: Any) -> dict[str, Any]:
    admission = _dict(value, "admission")
    _exact_keys(admission, _ALLOWED_ADMISSION, "admission")

    source_stage = _string(admission.get("source_stage"), "admission.source_stage", max_len=64)
    analysis_stage = _string(
        admission.get("analysis_stage"),
        "admission.analysis_stage",
        max_len=64,
    )
    risk_decision = _string(
        admission.get("risk_decision"),
        "admission.risk_decision",
        max_len=64,
    )
    severity = _string(
        admission.get("max_severity"),
        "admission.max_severity",
        max_len=32,
    )
    role = _string(
        admission.get("knowledge_role"),
        "admission.knowledge_role",
        max_len=64,
    )
    scope = _string(
        admission.get("learning_scope"),
        "admission.learning_scope",
        max_len=64,
    )
    structure_allowed = _bool(
        admission.get("structure_reference_allowed"),
        "admission.structure_reference_allowed",
    )
    implementation_allowed = _bool(
        admission.get("implementation_reference_allowed"),
        "admission.implementation_reference_allowed",
    )
    validated = _bool(
        admission.get("vorquel_validated"),
        "admission.vorquel_validated",
    )

    if source_stage != "RAW_UNTRUSTED":
        _fail("admission.source_stage", "must remain RAW_UNTRUSTED")
    if analysis_stage != "STATIC_ANALYZED":
        _fail("admission.analysis_stage", "must be STATIC_ANALYZED")
    if implementation_allowed:
        _fail("admission.implementation_reference_allowed", "must remain false in V0.1")
    if validated:
        _fail("admission.vorquel_validated", "must remain false in V0.1")

    expected = _EXPECTED_ROLE.get((risk_decision, severity))
    if expected is None:
        _fail("admission", "risk decision and severity pair is not valid in V0.1")
    if (role, scope) != expected:
        _fail("admission", "knowledge role/scope does not match risk decision")

    expected_structure_allowed = role in {
        "REFERENCE_PATTERN",
        "STRUCTURE_REFERENCE_RESTRICTED",
    }
    if structure_allowed != expected_structure_allowed:
        _fail(
            "admission.structure_reference_allowed",
            "does not match the knowledge role",
        )

    return {
        "source_stage": source_stage,
        "analysis_stage": analysis_stage,
        "risk_decision": risk_decision,
        "max_severity": severity,
        "knowledge_role": role,
        "learning_scope": scope,
        "structure_reference_allowed": structure_allowed,
        "implementation_reference_allowed": False,
        "vorquel_validated": False,
    }


def prepare_records(item: Any, *, analyzer_version: str) -> PreparedRecords:
    payload = _dict(item, "item")
    _exact_keys(payload, _ALLOWED_TOP_LEVEL, "item")

    schema_version = _string(
        payload.get("schema_version"),
        "schema_version",
        max_len=128,
    )
    if schema_version != "0.1":
        _fail("schema_version", "unsupported compiler schema version")

    if payload.get("kind") != "N8N_KNOWLEDGE_ITEM":
        _fail("kind", "must be N8N_KNOWLEDGE_ITEM")
    if payload.get("source_content_trust") != "UNTRUSTED_SOURCE_DATA":
        _fail("source_content_trust", "must remain UNTRUSTED_SOURCE_DATA")

    analyzer_version = _string(
        analyzer_version,
        "analyzer_version",
        max_len=128,
    )

    provenance = _validate_provenance(payload.get("provenance"))
    workflow = _validate_workflow(payload.get("workflow"))
    admission = _validate_admission(payload.get("admission"))
    findings = _validate_findings(payload.get("security_findings"))
    untrusted_text = _validate_untrusted_text(payload.get("untrusted_text"))
    executable = _validate_executable(payload.get("executable_snippets_untrusted"))

    encoded_size = len(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    if encoded_size > 5 * 1024 * 1024:
        _fail("item", "compiled item exceeds the 5 MiB V0.1 limit")

    return PreparedRecords(
        source={
            "source_repo": provenance["source_repo"],
            "source_commit": provenance["source_commit"],
            "source_path": provenance["source_path"],
            "content_sha256": provenance["sha256"],
            "source_kind": "N8N_WORKFLOW_JSON",
            "trust_level": "RAW_UNTRUSTED",
        },
        analysis={
            "analyzer_version": analyzer_version,
            "risk_decision": admission["risk_decision"],
            "max_severity": admission["max_severity"],
            "findings": findings,
        },
        knowledge={
            "compiler_schema_version": schema_version,
            "source_content_trust": "UNTRUSTED_SOURCE_DATA",
            "knowledge_role": admission["knowledge_role"],
            "learning_scope": admission["learning_scope"],
            "structure": workflow,
            "untrusted_text": untrusted_text,
            "executable_metadata": executable,
            "security_findings": findings,
            "implementation_reference_allowed": False,
            "vorquel_validated": False,
        },
    )
