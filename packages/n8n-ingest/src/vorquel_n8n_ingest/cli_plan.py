from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import ControlledIngestError, MAX_ITEMS, plan_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan a strict, non-persisting n8n corpus ingest manifest."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--analyzer-version", default="0.1.0")
    parser.add_argument("--count", type=int, default=MAX_ITEMS)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = plan_manifest(
            args.corpus_root,
            source_repo=args.source_repo,
            source_commit=args.source_commit,
            analyzer_version=args.analyzer_version,
            count=args.count,
        )
    except ControlledIngestError as exc:
        raise SystemExit(str(exc)) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PLANNED",
                "policy": manifest["policy"],
                "item_count": len(manifest["items"]),
                "paths": [item["source_path"] for item in manifest["items"]],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
