from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from .redaction import path_is_sensitive, redact_text

_SCHEMA_VERSION = "0.1"

_CODE_NODE_TYPES = {
    "n8n-nodes-base.code",
    "n8n-nodes-base.function",
    "n8n-nodes-base.functionItem",
}
_COMMAND_NODE_TYPES = {
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.ssh",
}
_TEXT_KEYS = {
    "content",
    "description",
    "instructions",
    "message",
    "prompt",
    "systemmessage",
    "text",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _flatten_strings(value: Any, prefix: str = "parameters"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}"
            yield from _flatten_strings(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _flatten_strings(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def _leaf(path: str) -> str:
    part = path.rsplit(".", 1)[-1]
    return part.split("[", 1)[0].lower()


def _is_expression(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("=") or "{{" in stripped or "}}" in stripped


def _trigger_type(node_type: str) -> bool:
    lowered = node_type.lower()
    return (
        "trigger" in lowered
        or lowered.endswith(".cron")
        or lowered.endswith(".scheduletrigger")
    )


def _node_record(node: dict[str, Any]) -> dict[str, Any]:
    parameters = node.get("parameters", {})
    node_type = str(node.get("type", "<missing>"))
    record: dict[str, Any] = {
        "name": str(node.get("name", "")),
        "type": node_type,
        "type_version": node.get("typeVersion"),
    }

    if isinstance(parameters, dict):
        resource = parameters.get("resource")
        operation = parameters.get("operation")
        if isinstance(resource, (str, int, float, bool)) or resource is None:
            record["resource"] = resource
        if isinstance(operation, (str, int, float, bool)) or operation is None:
            record["operation"] = operation

    credentials = node.get("credentials")
    if isinstance(credentials, dict):
        record["credential_types"] = sorted(str(key) for key in credentials)
    else:
        record["credential_types"] = []

    return record


def _extract_edges(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    connections = workflow.get("connections", {})
    if not isinstance(connections, dict):
        return edges

    for source_name, channels in connections.items():
        if not isinstance(channels, dict):
            continue
        for channel, outputs in channels.items():
            if not isinstance(outputs, list):
                continue
            for output_index, targets in enumerate(outputs):
                if not isinstance(targets, list):
                    continue
                for target in targets:
                    if not isinstance(target, dict):
                        continue
                    target_name = target.get("node")
                    if not isinstance(target_name, str):
                        continue
                    edges.append(
                        {
                            "source": str(source_name),
                            "target": target_name,
                            "channel": str(channel),
                            "source_output_index": output_index,
                            "target_input_index": int(target.get("index", 0) or 0),
                        }
                    )
    return sorted(
        edges,
        key=lambda edge: (
            edge["source"],
            edge["target"],
            edge["channel"],
            edge["source_output_index"],
            edge["target_input_index"],
        ),
    )


def _extract_untrusted_material(
    nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    texts: list[dict[str, Any]] = []
    executable: list[dict[str, Any]] = []

    for node in nodes:
        node_name = str(node.get("name", ""))
        node_type = str(node.get("type", ""))
        parameters = node.get("parameters", {})
        if not isinstance(parameters, (dict, list)):
            continue

        for path, value in _flatten_strings(parameters):
            if not value:
                continue

            executable_reason: str | None = None
            language = "expression"
            if node_type in _CODE_NODE_TYPES:
                executable_reason = "code_node"
                language = "javascript"
            elif node_type in _COMMAND_NODE_TYPES:
                executable_reason = "privileged_command"
                language = "shell_or_remote_command"
            elif _is_expression(value):
                executable_reason = "n8n_expression"

            if executable_reason is not None:
                executable.append(
                    {
                        "kind": "EXECUTABLE_SNIPPET_UNTRUSTED",
                        "node_name": node_name,
                        "node_type": node_type,
                        "json_path": path,
                        "reason": executable_reason,
                        "language": language,
                        "sha256": _sha256_text(value),
                        "char_count": len(value),
                        "content_persisted": False,
                    }
                )
                continue

            if _leaf(path) not in _TEXT_KEYS:
                continue

            item = {
                "kind": "UNTRUSTED_TEXT",
                "node_name": node_name,
                "node_type": node_type,
                "json_path": path,
                "sha256": _sha256_text(value),
                "char_count": len(value),
            }
            if path_is_sensitive(path):
                item["preview"] = "<redacted-sensitive-path>"
            else:
                item["preview"] = redact_text(value)
            texts.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(item["node_name"]),
            str(item["json_path"]),
            str(item["sha256"]),
        )

    return sorted(texts, key=sort_key), sorted(executable, key=sort_key)


def _admission(analysis_report: dict[str, Any]) -> dict[str, Any]:
    risk_decision = str(analysis_report.get("risk_decision", "REVIEW_REQUIRED"))
    severity = str(analysis_report.get("max_severity", "HIGH"))

    if risk_decision == "BLOCKED" or severity == "CRITICAL":
        role = "SECURITY_EXAMPLE"
        learning_scope = "security_only"
        structure_reference_allowed = False
    elif risk_decision == "REVIEW_REQUIRED" or severity == "HIGH":
        role = "QUARANTINED_REFERENCE"
        learning_scope = "review_only"
        structure_reference_allowed = False
    elif severity == "MEDIUM":
        role = "STRUCTURE_REFERENCE_RESTRICTED"
        learning_scope = "structure_only"
        structure_reference_allowed = True
    else:
        role = "REFERENCE_PATTERN"
        learning_scope = "structure_and_metadata"
        structure_reference_allowed = True

    return {
        "source_stage": "RAW_UNTRUSTED",
        "analysis_stage": "STATIC_ANALYZED",
        "risk_decision": risk_decision,
        "max_severity": severity,
        "knowledge_role": role,
        "learning_scope": learning_scope,
        "structure_reference_allowed": structure_reference_allowed,
        "implementation_reference_allowed": False,
        "vorquel_validated": False,
    }


def _safe_findings(analysis_report: dict[str, Any]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    findings = analysis_report.get("findings", [])
    if not isinstance(findings, list):
        return safe

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        safe.append(
            {
                "rule_id": finding.get("rule_id"),
                "severity": finding.get("severity"),
                "node_name": finding.get("node_name"),
                "node_type": finding.get("node_type"),
                "json_path": finding.get("json_path"),
            }
        )
    return sorted(
        safe,
        key=lambda item: (
            str(item.get("severity")),
            str(item.get("rule_id")),
            str(item.get("node_name")),
            str(item.get("json_path")),
        ),
    )


def compile_knowledge_item(
    workflow: dict[str, Any],
    analysis_report: dict[str, Any],
    *,
    source_repo: str,
    source_commit: str,
    source_path: str,
    source_sha256: str,
) -> dict[str, Any]:
    nodes_raw = workflow.get("nodes", [])
    if not isinstance(nodes_raw, list):
        raise ValueError("workflow nodes must be a list")
    nodes = [node for node in nodes_raw if isinstance(node, dict)]

    node_records = sorted(
        (_node_record(node) for node in nodes),
        key=lambda node: (node["type"], node["name"]),
    )
    type_counts = Counter(node["type"] for node in node_records)
    trigger_types = sorted(
        {node["type"] for node in node_records if _trigger_type(node["type"])}
    )
    integrations = sorted(type_counts)
    untrusted_texts, executable_snippets = _extract_untrusted_material(nodes)

    return {
        "schema_version": _SCHEMA_VERSION,
        "kind": "N8N_KNOWLEDGE_ITEM",
        "provenance": {
            "source_repo": source_repo,
            "source_commit": source_commit,
            "source_path": source_path,
            "sha256": source_sha256,
        },
        "workflow": {
            "name": str(workflow.get("name", "")),
            "node_count": len(node_records),
            "node_types": dict(sorted(type_counts.items())),
            "trigger_types": trigger_types,
            "integrations": integrations,
            "nodes": node_records,
            "edges": _extract_edges(workflow),
        },
        "admission": _admission(analysis_report),
        "security_findings": _safe_findings(analysis_report),
        "untrusted_text": untrusted_texts,
        "executable_snippets_untrusted": executable_snippets,
    }
