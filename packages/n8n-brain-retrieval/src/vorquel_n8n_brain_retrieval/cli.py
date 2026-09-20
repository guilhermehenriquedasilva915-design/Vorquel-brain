"""CLI for unified retrieval."""

from __future__ import annotations

import argparse
import json
import sys

from .db import DatabaseUnavailable, read_only_connection
from .retrieval import TASK_TYPES, retrieve_n8n_context
from .scope import Scope, ScopeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vorquel-brain-retrieve",
        description="Monta um CONTEXT PACK citado a partir da memoria da Vorquel.",
    )
    parser.add_argument("query", help="pergunta ou descricao da tarefa")
    parser.add_argument(
        "--task-type", default="ASK", choices=list(TASK_TYPES), help="intencao (default: ASK)"
    )
    parser.add_argument(
        "--scope",
        default="GLOBAL_VORQUEL",
        help="escopo, ex.: GLOBAL_VORQUEL ou CLIENT:acme (default: GLOBAL_VORQUEL)",
    )
    parser.add_argument("--environment", default="DEV", help="ambiente alvo (default: DEV)")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--json", action="store_true", help="saida JSON em vez de texto")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        scope = Scope.parse(args.scope)
    except ScopeError as exc:
        print(f"escopo invalido: {exc}", file=sys.stderr)
        return 2

    try:
        with read_only_connection() as conn:
            pack = retrieve_n8n_context(
                conn,
                query=args.query,
                task_type=args.task_type,
                scope=scope,
                environment=args.environment,
                limit=args.limit,
            )
    except DatabaseUnavailable as exc:
        print(f"store indisponivel: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(pack.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        print(pack.render())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
