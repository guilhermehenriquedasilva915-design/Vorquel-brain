from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

from .models import Finding
from .redaction import mask, redact_text

DANGEROUS_COMMAND_TYPES = {"n8n-nodes-base.executeCommand"}
SSH_TYPES = {"n8n-nodes-base.ssh"}
FILE_TYPES = {
    "n8n-nodes-base.readWriteFile",
    "n8n-nodes-base.readBinaryFile",
    "n8n-nodes-base.writeBinaryFile",
    "n8n-nodes-base.localFileTrigger",
}
CODE_TYPES = {
    "n8n-nodes-base.code",
    "n8n-nodes-base.function",
    "n8n-nodes-base.functionItem",
}
HTTP_TYPES = {"n8n-nodes-base.httpRequest"}

_DYNAMIC_CODE_PATTERNS = {
    "CODE_EVAL": re.compile(r"\beval\s*\(", re.I),
    "CODE_FUNCTION_CONSTRUCTOR": re.compile(r"\bnew\s+Function\s*\(", re.I),
    "CODE_CHILD_PROCESS": re.compile(r"child_process|execSync|spawnSync", re.I),
    "CODE_FILESYSTEM": re.compile(r"require\s*\(\s*['\"]fs['\"]\s*\)", re.I),
}

_SECRET_KEY = re.compile(r"(?i)(api[_ -]?key|token|password|passwd|secret|authorization)")
_PLACEHOLDER = re.compile(
    r"(?i)(YOUR[_ -]?[A-Z0-9_]*|"
    r"<[^>]*(token|secret|password|key)[^>]*>|"
    r"\{\{\s*\$(credentials|env)\b)"
)


def flatten_strings(value: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten_strings(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from flatten_strings(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def is_private_or_local_url(value: str) -> bool:
    if "{{" in value or "$env" in value:
        return False
    candidate = value.lstrip("=").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname.endswith(".local")
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _node_finding(
    rule_id: str,
    severity: str,
    message: str,
    node: dict[str, Any],
    *,
    path: str | None = None,
    evidence: str | None = None,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        node_name=str(node.get("name")) if node.get("name") is not None else None,
        node_type=str(node.get("type")) if node.get("type") is not None else None,
        json_path=path,
        evidence=redact_text(evidence) if evidence else None,
    )


def analyze_node(node: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    node_type = str(node.get("type", ""))
    parameters = node.get("parameters", {})
    flattened = list(flatten_strings(parameters, "parameters"))

    if node_type in DANGEROUS_COMMAND_TYPES:
        findings.append(
            _node_finding(
                "EXECUTE_COMMAND",
                "HIGH",
                "Workflow can execute operating-system commands.",
                node,
            )
        )
        for path, value in flattened:
            if "export:credentials" in value and "--decrypted" in value:
                findings.append(
                    _node_finding(
                        "DECRYPTED_CREDENTIAL_EXPORT",
                        "CRITICAL",
                        "Workflow exports n8n credentials in decrypted form.",
                        node,
                        path=path,
                        evidence="matched export:credentials with --decrypted",
                    )
                )

    if node_type in SSH_TYPES:
        findings.append(
            _node_finding(
                "SSH_EXECUTION",
                "HIGH",
                "Workflow can execute commands on a remote host through SSH.",
                node,
            )
        )

    if node_type in FILE_TYPES:
        findings.append(
            _node_finding(
                "FILESYSTEM_ACCESS",
                "MEDIUM",
                "Workflow reads from or writes to the local filesystem.",
                node,
            )
        )

    if node_type in HTTP_TYPES:
        findings.append(
            _node_finding(
                "NETWORK_REQUEST",
                "MEDIUM",
                "Workflow can make outbound HTTP requests.",
                node,
            )
        )
        for path, value in flattened:
            if path.endswith(".url") and is_private_or_local_url(value):
                findings.append(
                    _node_finding(
                        "PRIVATE_NETWORK_URL",
                        "HIGH",
                        "HTTP Request targets a local/private/link-local address.",
                        node,
                        path=path,
                        evidence=f"private_or_local_host={urlparse(value.lstrip('=').strip()).hostname}",
                    )
                )

    if node_type in CODE_TYPES:
        findings.append(
            _node_finding(
                "CUSTOM_CODE",
                "MEDIUM",
                "Workflow executes custom JavaScript code and requires manual review.",
                node,
            )
        )
        for path, value in flattened:
            for rule_id, pattern in _DYNAMIC_CODE_PATTERNS.items():
                if not pattern.search(value):
                    continue
                severity = "CRITICAL" if rule_id == "CODE_CHILD_PROCESS" else "HIGH"
                message = {
                    "CODE_EVAL": "Custom code uses eval().",
                    "CODE_FUNCTION_CONSTRUCTOR": (
                        "Custom code creates executable code dynamically."
                    ),
                    "CODE_CHILD_PROCESS": (
                        "Custom code references child process execution primitives."
                    ),
                    "CODE_FILESYSTEM": "Custom code imports filesystem access.",
                }[rule_id]
                findings.append(
                    _node_finding(
                        rule_id,
                        severity,
                        message,
                        node,
                        path=path,
                        evidence=f"matched rule {rule_id}",
                    )
                )

    for path, value in flattened:
        leaf = path.rsplit(".", 1)[-1].lower()
        if leaf in {"id", "name"} and ".credentials." in path.lower():
            continue
        if not _SECRET_KEY.search(path):
            continue
        if _PLACEHOLDER.search(value) or not value.strip() or len(value.strip()) < 8:
            continue
        findings.append(
            _node_finding(
                "POSSIBLE_HARDCODED_SECRET",
                "HIGH",
                "A secret-like field appears to contain a hardcoded value.",
                node,
                path=path,
                evidence=mask(value.strip()),
            )
        )

    return findings


def analyze_workflow_level(workflow: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    nodes = [node for node in workflow.get("nodes", []) if isinstance(node, dict)]
    node_types = {str(node.get("type", "")) for node in nodes}

    privileged = bool(node_types & (DANGEROUS_COMMAND_TYPES | SSH_TYPES))
    ai_like = any(
        (
            "agent" in str(node.get("type", "")).lower()
            or "lmchat" in str(node.get("type", "")).lower()
        )
        and str(node.get("type", "")) != "n8n-nodes-base.noOp"
        for node in nodes
    )
    if privileged and ai_like:
        findings.append(
            Finding(
                rule_id="AI_WITH_PRIVILEGED_EXECUTION",
                severity="CRITICAL",
                message=(
                    "Workflow combines AI/agent functionality with command or SSH execution. "
                    "Treat as prompt-injection-sensitive until manually proven safe."
                ),
            )
        )

    return findings
