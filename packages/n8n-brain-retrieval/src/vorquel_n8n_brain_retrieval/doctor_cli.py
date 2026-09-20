"""CLI for `brain doctor`."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .doctor import Status, run_doctor

EXIT_CODES = {Status.READY: 0, Status.READY_WITH_LIMITS: 0, Status.BLOCKED: 1}


def _default_repo_root() -> Path:
    # src/vorquel_n8n_brain_retrieval/doctor_cli.py -> packages/... -> repo root
    return Path(__file__).resolve().parents[4]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vorquel-brain-doctor",
        description="Verifica se o Brain esta utilizavel, sem revelar segredos.",
    )
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--watch-root",
        type=Path,
        default=None,
        help="caminho do repo Vorquel-watch (ou env VORQUEL_WATCH_ROOT)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="sai com codigo 1 tambem em READY_WITH_LIMITS",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _default_repo_root()
    watch_env = os.environ.get("VORQUEL_WATCH_ROOT")
    watch_root = args.watch_root or (Path(watch_env) if watch_env else None)

    report = run_doctor(repo_root, watch_root)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(report.render())

    if args.strict and report.overall is not Status.READY:
        return 1
    return EXIT_CODES[report.overall]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
