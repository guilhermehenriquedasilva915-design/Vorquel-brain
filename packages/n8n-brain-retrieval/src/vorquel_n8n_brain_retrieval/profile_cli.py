"""CLI that records an N8N_ENVIRONMENT_PROFILE from observed facts.

Everything written here is either read from the instance's own unauthenticated
endpoints or handed in by the operator after enumerating the MCP surface. The
command never asks n8n for a credential payload, and refuses to write a profile
that trips the secret scan.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .environment_profile import (
    ProfileError,
    build_profile,
    default_profile_path,
    write_profile,
)


def _get_json(url: str, timeout: float) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _read_tools(path: Path | None) -> list[str]:
    if path is None:
        return []
    tools: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        # Accept either the bare tool name or the client-qualified form.
        tools.append(name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name)
    return tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vorquel-n8n-profile",
        description="Grava o N8N_ENVIRONMENT_PROFILE sanitizado da instancia DEV.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5678")
    parser.add_argument("--environment", default="DEV")
    parser.add_argument(
        "--tools-from",
        type=Path,
        default=None,
        help="arquivo com um nome de tool MCP por linha, enumerado no runtime",
    )
    parser.add_argument(
        "--n8n-version",
        default=None,
        help="versao observada (o /rest/settings publico nao a expoe)",
    )
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--print", action="store_true", help="imprime o perfil gravado")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = args.base_url.rstrip("/")

    health = _get_json(f"{base}/healthz", args.timeout)
    if health is None:
        print(f"instancia inalcancavel em {base}: nada foi gravado")
        return 1

    settings = _get_json(f"{base}/rest/settings", args.timeout) or {}
    data = settings.get("data") if isinstance(settings, dict) else {}
    data = data if isinstance(data, dict) else {}

    resource = (
        _get_json(f"{base}/.well-known/oauth-protected-resource/mcp-server/http", args.timeout)
        or {}
    )
    scopes = resource.get("scopes_supported") or []
    mcp_server_url = resource.get("resource")

    version = args.n8n_version or data.get("versionCli") or "unknown"
    instance_id = data.get("instanceId") or "unknown"

    try:
        profile = build_profile(
            instance_id=str(instance_id),
            base_url=base,
            n8n_version=str(version),
            environment=args.environment,
            mcp_server_url=str(mcp_server_url) if mcp_server_url else None,
            mcp_tools=_read_tools(args.tools_from),
            mcp_scopes=[str(s) for s in scopes],
            project_id=args.project_id,
        )
    except (ProfileError, ValueError) as exc:
        print(f"perfil recusado: {exc}")
        return 1

    target = write_profile(profile, args.out or default_profile_path())
    print(f"profile gravado em {target}")
    print(
        f"  environment={profile['environment']} n8n={profile['n8n_version']} "
        f"tools={len(profile['mcp']['tools'])} scopes={len(profile['mcp']['scopes'])}"
    )
    if args.print:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
