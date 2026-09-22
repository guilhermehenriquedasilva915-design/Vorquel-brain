"""N8N_ENVIRONMENT_PROFILE — the sanitized facts we are allowed to build against.

The profile records what an n8n instance *is* (version, environment, node and
tool surface) so that planning stops guessing. It is deliberately a poor place
to hide a secret: :func:`scan_for_secrets` refuses any profile carrying a
password, token, API key, credential payload or encryption key, and the loader
refuses to return a profile that fails that scan.

It also records the MCP tool names that were actually enumerated at runtime.
That is the difference between "production is denied" as a belief and as a
fact: :func:`audit_tool_policy` can only compare a denylist against a tool
surface someone really observed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROFILE_ENV_VAR = "VORQUEL_N8N_ENVIRONMENT_PROFILE"
PROFILE_VERSION = 1

#: How old a profile may be before it stops counting as a current observation.
MAX_PROFILE_AGE_DAYS = 30

#: Keys that must never appear anywhere in a profile, at any depth.
FORBIDDEN_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|apikey|encryption[_-]?key"
    r"|client[_-]?secret|private[_-]?key|authorization|cookie|dsn"
    r"|connection[_-]?string|service[_-]?role|credential_data|credential_payload)",
    re.IGNORECASE,
)

#: Values that look like a credential even under an innocent key.
FORBIDDEN_VALUE_PATTERN = re.compile(
    r"(postgres(?:ql)?://[^\s]*:[^\s]*@"  # DSN with an inline password
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."  # JWT
    r"|sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,})",
)

#: Real tool names that must be denied outright before any BUILD run.
#:
#: These are not guesses. Each one either changes production state, destroys a
#: workflow, or reaches a third party with a real credential.
REQUIRED_DENY_TOOLS = frozenset(
    {
        "unpublish_workflow",
        "archive_workflow",
        "restore_workflow_version",
        "explore_node_resources",
        "create_data_table",
        "rename_data_table",
        "add_data_table_column",
        "rename_data_table_column",
        "delete_data_table_column",
        "add_data_table_rows",
    }
)

#: Real tool names that must never be silently allowed: they mutate the
#: instance or execute nodes, so they need a human in the loop.
REQUIRED_ASK_TOOLS = frozenset(
    {
        "create_workflow_from_code",
        "update_workflow",
        "test_workflow",
        "prepare_workflow_pin_data",
    }
)

MCP_TOOL_PREFIX = "mcp__n8n__"


class ProfileError(RuntimeError):
    """A profile exists but cannot be trusted."""


@dataclass(frozen=True)
class PolicyFinding:
    """One way the configured policy disagrees with the observed tool surface."""

    tool: str
    problem: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.tool}: {self.problem}"


def default_profile_path() -> Path:
    """Where the profile lives when nobody says otherwise.

    Outside the repository on purpose. Vorquel-brain is public, and a profile
    names a specific machine's instance even after sanitizing.
    """
    override = os.environ.get(PROFILE_ENV_VAR)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "Vorquel" / "n8n-dev" / "environment-profile.json"
    return Path.home() / ".vorquel" / "n8n-dev" / "environment-profile.json"


def sanitize_base_url(raw: str) -> str:
    """Keep scheme, host and port. Drop anything that could carry a credential."""
    match = re.match(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://(?P<rest>.*)$", raw.strip())
    if not match:
        raise ValueError("base_url sem esquema")
    rest = match.group("rest")
    authority = rest.split("/", 1)[0]
    # user:pass@host -> host
    host = authority.rsplit("@", 1)[-1]
    if not host:
        raise ValueError("base_url sem host")
    return f"{match.group('scheme')}://{host}"


def sanitize_instance_id(raw: str, keep: int = 12) -> str:
    """An instance id identifies a machine. Keep enough to correlate, not to clone."""
    raw = raw.strip()
    if len(raw) <= keep:
        return raw
    return f"{raw[:keep]}..."


def _walk(node: Any, path: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            found.append((here, key))
            found.extend(_walk(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_walk(value, f"{path}[{index}]"))
    else:
        found.append((path, node))
    return found


def scan_for_secrets(profile: dict[str, Any]) -> list[str]:
    """Return the paths of anything that looks like a secret. Empty means clean."""
    offenders: list[str] = []
    for path, value in _walk(profile):
        if isinstance(value, str):
            # A dict key arrives here as its own value; check both shapes.
            if FORBIDDEN_KEY_PATTERN.search(path):
                offenders.append(path)
                continue
            if FORBIDDEN_VALUE_PATTERN.search(value):
                offenders.append(path)
    return sorted(set(offenders))


def build_profile(
    *,
    instance_id: str,
    base_url: str,
    n8n_version: str,
    environment: str,
    mcp_server_url: str | None,
    mcp_tools: list[str],
    mcp_scopes: list[str],
    node_types: list[dict[str, Any]] | None = None,
    community_nodes: list[str] | None = None,
    credential_aliases: list[dict[str, str]] | None = None,
    workflows: list[dict[str, Any]] | None = None,
    project_id: str | None = None,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble a profile, sanitizing as it goes, and refuse to emit a leaky one."""
    moment = checked_at or datetime.now(UTC)
    profile: dict[str, Any] = {
        "profile_version": PROFILE_VERSION,
        "checked_at": moment.astimezone(UTC).isoformat(),
        "environment": environment.upper(),
        "instance_id": sanitize_instance_id(instance_id),
        "base_url": sanitize_base_url(base_url),
        "n8n_version": n8n_version,
        "project_id": project_id,
        "mcp": {
            "server_url": sanitize_base_url(mcp_server_url) if mcp_server_url else None,
            "server_path": _url_path(mcp_server_url) if mcp_server_url else None,
            "tools": sorted(set(mcp_tools)),
            "scopes": sorted(set(mcp_scopes)),
        },
        "node_types": node_types or [],
        "community_nodes": community_nodes or [],
        # Aliases and types only. A payload never reaches this file.
        "credential_aliases": credential_aliases or [],
        "workflows": workflows or [],
    }
    offenders = scan_for_secrets(profile)
    if offenders:
        raise ProfileError(f"perfil recusado, campos suspeitos: {', '.join(offenders)}")
    return profile


def _url_path(raw: str) -> str:
    rest = raw.split("://", 1)[-1]
    _, _, path = rest.partition("/")
    return f"/{path}" if path else "/"


def write_profile(profile: dict[str, Any], path: Path | None = None) -> Path:
    target = path or default_profile_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def load_profile(path: Path | None = None) -> dict[str, Any] | None:
    """Return the profile, or None when there is none. Raise if it is not safe."""
    target = path or default_profile_path()
    if not target.is_file():
        return None
    try:
        profile = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"perfil ilegivel: {exc.msg}") from exc
    if not isinstance(profile, dict):
        raise ProfileError("perfil nao e um objeto")
    offenders = scan_for_secrets(profile)
    if offenders:
        raise ProfileError(f"perfil contem campos suspeitos: {', '.join(offenders)}")
    return profile


def profile_age_days(profile: dict[str, Any], now: datetime | None = None) -> float | None:
    raw = profile.get("checked_at")
    if not isinstance(raw, str):
        return None
    try:
        seen = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    moment = now or datetime.now(UTC)
    return (moment - seen).total_seconds() / 86400.0


def observed_tools(profile: dict[str, Any]) -> list[str]:
    mcp = profile.get("mcp")
    if not isinstance(mcp, dict):
        return []
    tools = mcp.get("tools")
    if not isinstance(tools, list):
        return []
    return [t for t in tools if isinstance(t, str)]


def _bucket(permissions: dict[str, Any], name: str) -> set[str]:
    entries = permissions.get(name) or []
    return {
        entry[len(MCP_TOOL_PREFIX) :]
        for entry in entries
        if isinstance(entry, str) and entry.startswith(MCP_TOOL_PREFIX)
    }


def audit_tool_policy(
    tools: list[str],
    permissions: dict[str, Any],
) -> list[PolicyFinding]:
    """Compare a denylist against a tool surface that was really enumerated.

    Every finding is a concrete disagreement, never a style opinion.
    """
    allow = _bucket(permissions, "allow")
    ask = _bucket(permissions, "ask")
    deny = _bucket(permissions, "deny")
    surface = set(tools)
    findings: list[PolicyFinding] = []

    for tool in sorted(surface):
        pairs = (("allow", allow), ("ask", ask), ("deny", deny))
        buckets = [name for name, bucket in pairs if tool in bucket]
        if not buckets:
            findings.append(PolicyFinding(tool, "exposto pelo MCP e sem regra em settings.json"))
        elif len(buckets) > 1:
            findings.append(PolicyFinding(tool, f"em mais de um bucket: {', '.join(buckets)}"))

    for tool in sorted(REQUIRED_DENY_TOOLS & surface):
        if tool not in deny:
            findings.append(
                PolicyFinding(tool, "efeito real fora do DEV controlado e nao esta em deny")
            )

    for tool in sorted(REQUIRED_ASK_TOOLS & surface):
        if tool in allow:
            findings.append(
                PolicyFinding(tool, "muta a instancia e esta em allow, deveria ser ask")
            )
        elif tool not in ask and tool not in deny:
            findings.append(PolicyFinding(tool, "muta a instancia e nao esta em ask nem deny"))

    return findings


def dead_deny_rules(tools: list[str], permissions: dict[str, Any]) -> list[str]:
    """Denied n8n tool names that the live MCP does not expose.

    Harmless as forward-looking guards, but they must never be mistaken for
    protection that is currently doing something.
    """
    return sorted(_bucket(permissions, "deny") - set(tools))
