from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg

from .common import ControlledIngestionError
from .ingest import ingest_manifest, load_manifest

_DATABASE_ENV = "N8N_BRAIN_DATABASE_URL"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or persist only workflows explicitly listed in a manifest."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist after complete validation. Without this flag the command is dry-run.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = load_manifest(args.manifest)
    except ControlledIngestionError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.persist:
        try:
            result = ingest_manifest(args.corpus_root, manifest, persist=False)
        except ControlledIngestionError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(result, sort_keys=True))
        return 0

    dsn = os.environ.get(_DATABASE_ENV)
    if not dsn:
        raise SystemExit(f"{_DATABASE_ENV} is required with --persist")

    try:
        with psycopg.connect(dsn) as connection:
            result = ingest_manifest(
                args.corpus_root,
                manifest,
                connection=connection,
                persist=True,
            )
    except ControlledIngestionError as exc:
        raise SystemExit(str(exc)) from exc
    except psycopg.Error as exc:
        raise SystemExit(
            f"database write failed ({exc.__class__.__name__}); connection details withheld"
        ) from exc

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
