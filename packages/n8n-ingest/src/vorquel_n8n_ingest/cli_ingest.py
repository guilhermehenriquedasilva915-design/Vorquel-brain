from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg

from vorquel_n8n_knowledge_writer.writer import (
    ImmutableDriftError,
    write_prepared_records_batch,
)

from .core import ControlledIngestError, compile_manifest_items

_DATABASE_ENV = "N8N_BRAIN_DATABASE_URL"
_MAX_MANIFEST_BYTES = 64 * 1024


def _read_manifest(path: Path) -> dict:
    if path.is_symlink():
        raise ControlledIngestError("manifest symlink is not allowed")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ControlledIngestError(
            f"unable to stat manifest ({exc.__class__.__name__})"
        ) from exc
    if size > _MAX_MANIFEST_BYTES:
        raise ControlledIngestError("manifest exceeds 64 KiB limit")

    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ControlledIngestError("manifest is not readable valid JSON") from exc
    if not isinstance(payload, dict):
        raise ControlledIngestError("manifest JSON must be an object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or persist an explicit controlled n8n ingest manifest."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist after complete pre-validation. Default is dry-run.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = _read_manifest(args.manifest)
        compiled = compile_manifest_items(args.corpus_root, manifest)
    except ControlledIngestError as exc:
        raise SystemExit(str(exc)) from exc

    summary = [
        {
            "source_path": item.source_path,
            "sha256": item.sha256,
            "risk_decision": item.risk_decision,
            "knowledge_role": item.knowledge_role,
            "node_count": item.node_count,
        }
        for item in compiled
    ]

    if not args.persist:
        print(
            json.dumps(
                {
                    "status": "VALIDATED_DRY_RUN",
                    "item_count": len(compiled),
                    "items": summary,
                },
                sort_keys=True,
            )
        )
        return 0

    dsn = os.environ.get(_DATABASE_ENV)
    if not dsn:
        raise SystemExit(f"{_DATABASE_ENV} is required with --persist")

    try:
        with psycopg.connect(dsn) as connection:
            results = write_prepared_records_batch(
                connection,
                [item.records for item in compiled],
            )
    except ImmutableDriftError as exc:
        raise SystemExit(f"immutable drift detected: {exc}") from exc
    except psycopg.Error as exc:
        raise SystemExit(
            f"database ingest failed ({exc.__class__.__name__}); connection details withheld"
        ) from exc

    print(
        json.dumps(
            {
                "status": "PERSISTED",
                "item_count": len(results),
                "items": [
                    {
                        **item_summary,
                        "created": {
                            "source": result.source_created,
                            "analysis": result.analysis_created,
                            "knowledge": result.knowledge_created,
                        },
                    }
                    for item_summary, result in zip(summary, results, strict=True)
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
