from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg

from .validation import KnowledgeItemValidationError, prepare_records
from .writer import ImmutableDriftError, write_prepared_records

DEFAULT_MAX_ITEM_BYTES = 5 * 1024 * 1024
_DATABASE_ENV = "N8N_BRAIN_DATABASE_URL"


def _read_item(path: Path, *, max_bytes: int) -> dict[str, Any]:
    if path.is_symlink():
        raise KnowledgeItemValidationError("item: symlink input is not allowed")

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise KnowledgeItemValidationError(
            f"item: unable to stat input ({exc.__class__.__name__})"
        ) from exc

    if size > max_bytes:
        raise KnowledgeItemValidationError(
            f"item: exceeds configured size limit ({max_bytes} bytes)"
        )

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise KnowledgeItemValidationError(
            f"item: unable to read input ({exc.__class__.__name__})"
        ) from exc

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise KnowledgeItemValidationError("item: invalid JSON") from exc

    if not isinstance(payload, dict):
        raise KnowledgeItemValidationError("item: JSON must be an object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and append a compiled n8n knowledge item."
    )
    parser.add_argument("item", type=Path)
    parser.add_argument("--analyzer-version", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-item-mb",
        type=float,
        default=DEFAULT_MAX_ITEM_BYTES / (1024 * 1024),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_item_mb <= 0:
        raise SystemExit("--max-item-mb must be greater than zero")

    try:
        payload = _read_item(
            args.item,
            max_bytes=int(args.max_item_mb * 1024 * 1024),
        )
        records = prepare_records(
            payload,
            analyzer_version=args.analyzer_version,
        )
    except KnowledgeItemValidationError as exc:
        raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "VALIDATED",
                    "dry_run": True,
                    "source_sha256": records.source["content_sha256"],
                    "risk_decision": records.analysis["risk_decision"],
                    "knowledge_role": records.knowledge["knowledge_role"],
                },
                sort_keys=True,
            )
        )
        return 0

    dsn = os.environ.get(_DATABASE_ENV)
    if not dsn:
        raise SystemExit(f"{_DATABASE_ENV} is required unless --dry-run is used")

    try:
        with psycopg.connect(dsn) as connection:
            result = write_prepared_records(connection, records)
    except ImmutableDriftError as exc:
        raise SystemExit(f"immutable drift detected: {exc}") from exc
    except psycopg.Error as exc:
        raise SystemExit(
            f"database write failed ({exc.__class__.__name__}); connection details withheld"
        ) from exc

    print(
        json.dumps(
            {
                "status": "PERSISTED",
                "source_id": result.source_id,
                "analysis_id": result.analysis_id,
                "knowledge_id": result.knowledge_id,
                "created": {
                    "source": result.source_created,
                    "analysis": result.analysis_created,
                    "knowledge": result.knowledge_created,
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
