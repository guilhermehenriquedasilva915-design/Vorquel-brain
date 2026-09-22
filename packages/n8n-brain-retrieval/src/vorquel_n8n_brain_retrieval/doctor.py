"""brain doctor — is the Brain usable right now, and with what limits?

Reports readiness without ever revealing a secret. It prints whether a
credential is configured, never its value, and never asks n8n or Postgres for
credential payloads.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .db import (
    ENV_VAR,
    DatabaseUnavailable,
    column_exists,
    fetch_all,
    function_exists,
    read_only_connection,
)
from .environment_profile import (
    MAX_PROFILE_AGE_DAYS,
    ProfileError,
    audit_tool_policy,
    dead_deny_rules,
    load_profile,
    observed_tools,
    profile_age_days,
)


class Status(StrEnum):
    READY = "READY"
    READY_WITH_LIMITS = "READY_WITH_LIMITS"
    BLOCKED = "BLOCKED"


@dataclass
class Check:
    name: str
    status: Status
    detail: str


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: Status, detail: str) -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def overall(self) -> Status:
        if any(c.status is Status.BLOCKED for c in self.checks):
            return Status.BLOCKED
        if any(c.status is Status.READY_WITH_LIMITS for c in self.checks):
            return Status.READY_WITH_LIMITS
        return Status.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.value,
            "checks": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
        }

    def render(self) -> str:
        width = max((len(c.name) for c in self.checks), default=0)
        lines = [f"BRAIN DOCTOR - {self.overall.value}", ""]
        for c in self.checks:
            mark = {
                Status.READY: "ok  ",
                Status.READY_WITH_LIMITS: "warn",
                Status.BLOCKED: "BLOCK",
            }[c.status]
            lines.append(f"  [{mark:>5}] {c.name.ljust(width)}  {c.detail}")
        return "\n".join(lines)


def _check_claude(report: DoctorReport, repo_root: Path) -> dict[str, Any]:
    skill = repo_root / ".claude" / "skills" / "n8n-brain" / "SKILL.md"
    if skill.is_file():
        refs = sorted((skill.parent / "references").glob("*.md"))
        report.add(
            "claude.skill",
            Status.READY,
            f"n8n-brain presente ({len(refs)} procedimentos)",
        )
    else:
        report.add("claude.skill", Status.BLOCKED, "Skill n8n-brain ausente")

    settings = repo_root / ".claude" / "settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.add("claude.permissions", Status.BLOCKED, f"settings.json invalido: {exc.msg}")
            return {}
        perms = data.get("permissions") or {}
        deny = perms.get("deny") or []
        if deny:
            report.add(
                "claude.permissions",
                Status.READY,
                f"{len(perms.get('allow') or [])} allow / {len(deny)} deny configurados",
            )
        else:
            report.add(
                "claude.permissions",
                Status.READY_WITH_LIMITS,
                "settings.json sem denylist: tools de producao nao estao bloqueadas",
            )
        return perms
    else:
        report.add(
            "claude.permissions",
            Status.BLOCKED,
            ".claude/settings.json ausente: nenhuma allow/denylist real de MCP",
        )
    return {}


def _check_knowledge(report: DoctorReport) -> None:
    dsn = os.environ.get(ENV_VAR)
    if not dsn:
        report.add(
            "knowledge.connection",
            Status.BLOCKED,
            f"{ENV_VAR} nao definido (valor nunca e exibido)",
        )
        return
    try:
        with read_only_connection(dsn) as conn:
            report.add("knowledge.connection", Status.READY, "conexao read-only estabelecida")

            schemas = {
                r["nspname"]
                for r in fetch_all(
                    conn,
                    "select nspname from pg_namespace "
                    "where nspname in ('vorquel_knowledge','n8n_brain')",
                )
            }
            for schema in ("vorquel_knowledge", "n8n_brain"):
                report.add(
                    f"knowledge.schema.{schema}",
                    Status.READY if schema in schemas else Status.BLOCKED,
                    "presente" if schema in schemas else "ausente",
                )

            if "vorquel_knowledge" in schemas:
                scoped = column_exists(
                    conn, "vorquel_knowledge", "knowledge_items", "scope_type"
                )
                report.add(
                    "safety.scope_isolation",
                    Status.READY if scoped else Status.BLOCKED,
                    "scope_type/scope_id presentes"
                    if scoped
                    else "migration 0021 nao aplicada: isolamento entre clientes IMPOSSIVEL",
                )
                rpc = function_exists(conn, "public", "search_knowledge_items_scoped")
                report.add(
                    "knowledge.scoped_rpc",
                    Status.READY if rpc else Status.READY_WITH_LIMITS,
                    "search_knowledge_items_scoped disponivel"
                    if rpc
                    else "RPC com escopo ausente: retrieval usa fallback direto",
                )
                generic = column_exists(
                    conn, "vorquel_knowledge", "knowledge_sources", "locator_kind"
                )
                report.add(
                    "knowledge.generic_provenance",
                    Status.READY if generic else Status.READY_WITH_LIMITS,
                    "locator_kind presente"
                    if generic
                    else "so provenance de midia: PDF/repo/workflow nao sao citaveis",
                )
                counts = fetch_all(
                    conn,
                    "select count(*) filter (where lifecycle_state = 'ACTIVE') as active, "
                    "count(*) as total from vorquel_knowledge.knowledge_items",
                )[0]
                report.add(
                    "knowledge.corpus",
                    Status.READY if counts["active"] else Status.READY_WITH_LIMITS,
                    f"{counts['active']} ACTIVE de {counts['total']} itens",
                )

            if "n8n_brain" in schemas:
                has_exp = column_exists(
                    conn, "n8n_brain", "operational_experiences", "experience_id"
                )
                report.add(
                    "safety.run_journal",
                    Status.READY if has_exp else Status.READY_WITH_LIMITS,
                    "operational_experiences + build_runs presentes"
                    if has_exp
                    else "migration 20260920_004 nao aplicada: sem memoria operacional",
                )
                n = fetch_all(conn, "select count(*) as n from n8n_brain.knowledge_items")[0]["n"]
                report.add(
                    "n8n_brain.structural_corpus",
                    Status.READY if n else Status.READY_WITH_LIMITS,
                    f"{n} referencias estruturais persistidas",
                )
    except DatabaseUnavailable as exc:
        report.add("knowledge.connection", Status.BLOCKED, str(exc))


def _port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_n8n(report: DoctorReport, permissions: dict[str, Any]) -> None:
    base = os.environ.get("N8N_BASE_URL")
    if not base:
        report.add(
            "n8n.instance",
            Status.BLOCKED,
            "N8N_BASE_URL nao definido: nenhuma instancia n8n conhecida",
        )
    else:
        host = base.split("//", 1)[-1].split("/", 1)[0]
        hostname, _, port_s = host.partition(":")
        port = int(port_s) if port_s.isdigit() else (443 if base.startswith("https") else 80)
        reachable = _port_open(hostname, port)
        report.add(
            "n8n.instance",
            Status.READY if reachable else Status.BLOCKED,
            f"{hostname}:{port} {'alcancavel' if reachable else 'inalcancavel'}",
        )

    env = os.environ.get("N8N_ENVIRONMENT", "").upper()
    if env and env != "DEV":
        report.add(
            "n8n.environment",
            Status.BLOCKED,
            f"N8N_ENVIRONMENT={env}: mutacoes bloqueadas fora de DEV",
        )
    elif env == "DEV":
        report.add("n8n.environment", Status.READY, "DEV")
    else:
        report.add(
            "n8n.environment",
            Status.BLOCKED,
            "N8N_ENVIRONMENT nao declarado: assume-se nao-DEV e bloqueia mutacao",
        )

    profile, profile_error = _load_profile_safely()
    tools = observed_tools(profile) if profile else []

    _check_n8n_mcp(report, tools, configured=_mcp_server_configured())
    _check_n8n_deny_rules(report, tools, permissions)
    _check_n8n_profile(report, profile, profile_error)


def _load_profile_safely() -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_profile(), None
    except ProfileError as exc:
        return None, str(exc)


def _mcp_server_configured() -> bool:
    """Is an n8n MCP server registered with Claude Code on this machine?

    Read as a fact from the client's own config. A profile can go stale; this
    cannot say more than "a server by that name is configured".
    """
    config = Path.home() / ".claude.json"
    if not config.is_file():
        return False
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    def _has_n8n(servers: Any) -> bool:
        return isinstance(servers, dict) and any(
            "n8n" in str(name).lower() for name in servers
        )

    if _has_n8n(data.get("mcpServers")):
        return True
    projects = data.get("projects")
    if isinstance(projects, dict):
        return any(
            _has_n8n(entry.get("mcpServers"))
            for entry in projects.values()
            if isinstance(entry, dict)
        )
    return False


def _check_n8n_mcp(report: DoctorReport, tools: list[str], *, configured: bool) -> None:
    if tools:
        report.add(
            "n8n.mcp",
            Status.READY,
            f"{len(tools)} tools reais enumeradas e registradas no profile",
        )
    elif configured:
        report.add(
            "n8n.mcp",
            Status.READY_WITH_LIMITS,
            "MCP n8n configurado, mas superficie nunca enumerada: rode vorquel-n8n-profile",
        )
    else:
        report.add(
            "n8n.mcp",
            Status.BLOCKED,
            "nenhum MCP n8n configurado: build/test/debug indisponiveis",
        )


def _check_n8n_deny_rules(
    report: DoctorReport, tools: list[str], permissions: dict[str, Any]
) -> None:
    if not permissions:
        report.add(
            "n8n.deny_rules",
            Status.BLOCKED,
            "sem permissions em settings.json: nada esta bloqueado",
        )
        return
    if not tools:
        # Refusing to grade a denylist against a surface nobody observed is the
        # whole point: an unverified rule is not protection.
        report.add(
            "n8n.deny_rules",
            Status.READY_WITH_LIMITS,
            "superficie real desconhecida: denylist nao verificavel",
        )
        return

    findings = audit_tool_policy(tools, permissions)
    dead = dead_deny_rules(tools, permissions)
    if findings:
        report.add(
            "n8n.deny_rules",
            Status.BLOCKED,
            f"{len(findings)} divergencia(s) real(is): {findings[0]}",
        )
        return
    detail = f"{len(tools)} tools cobertas, nenhuma sem regra"
    if dead:
        detail += f"; {len(dead)} regra(s) deny sem tool correspondente (guarda futura)"
    report.add("n8n.deny_rules", Status.READY, detail)


def _check_n8n_profile(
    report: DoctorReport, profile: dict[str, Any] | None, error: str | None
) -> None:
    if error:
        report.add("n8n.environment_profile", Status.BLOCKED, error)
        return
    if profile is None:
        report.add(
            "n8n.environment_profile",
            Status.BLOCKED,
            "N8N_ENVIRONMENT_PROFILE ausente: planejamento sem referencia da instancia",
        )
        return
    env = str(profile.get("environment", "")).upper()
    if env != "DEV":
        report.add(
            "n8n.environment_profile",
            Status.BLOCKED,
            f"profile declara environment={env or 'desconhecido'}: mutacao so e permitida em DEV",
        )
        return
    age = profile_age_days(profile)
    if age is None:
        report.add(
            "n8n.environment_profile",
            Status.READY_WITH_LIMITS,
            "profile sem checked_at valido: idade desconhecida",
        )
        return
    if age > MAX_PROFILE_AGE_DAYS:
        report.add(
            "n8n.environment_profile",
            Status.READY_WITH_LIMITS,
            f"profile observado ha {age:.0f} dias: reconfirme a instancia",
        )
        return
    report.add(
        "n8n.environment_profile",
        Status.READY,
        f"DEV, n8n {profile.get('n8n_version', '?')}, observado ha {age:.1f} dia(s)",
    )


def _check_watch(report: DoctorReport, watch_root: Path | None) -> None:
    if watch_root is None or not watch_root.is_dir():
        report.add(
            "watch.runtime",
            Status.READY_WITH_LIMITS,
            "repo Vorquel-watch nao localizado: LEARN de video indisponivel",
        )
        return
    skill = watch_root / "skills" / "claude" / "watch" / "SKILL.md"
    report.add(
        "watch.runtime",
        Status.READY if skill.is_file() else Status.READY_WITH_LIMITS,
        "skill watch presente" if skill.is_file() else "skill watch ausente",
    )
    report.add(
        "watch.media_tools",
        Status.READY if shutil.which("ffmpeg") else Status.READY_WITH_LIMITS,
        "ffmpeg disponivel" if shutil.which("ffmpeg") else "ffmpeg ausente: transcricao limitada",
    )


def run_doctor(repo_root: Path, watch_root: Path | None = None) -> DoctorReport:
    report = DoctorReport()
    permissions = _check_claude(report, repo_root)
    _check_knowledge(report)
    _check_watch(report, watch_root)
    _check_n8n(report, permissions)
    return report
