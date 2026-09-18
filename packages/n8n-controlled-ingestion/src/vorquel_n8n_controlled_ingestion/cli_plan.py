from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import MAX_MANIFEST_ITEMS, ControlledIngestionError
from .planner import build_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan a deterministic strict-safe n8n ingestion manifest."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--analyzer-version", required=True)
    parser.add_argument("--max-items", type=int, default=MAX_MANIFEST_ITEMS)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = build_manifest(
            args.corpus_root,
            source_repo=args.source_repo,
            source_commit=args.source_commit,
            analyzer_version=args.analyzer_version,
            max_items=args.max_items,
        )
    except ControlledIngestionError as exc:
        raise SystemExit(str(exc)) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "PLANNED",
                "item_count": len(manifest["items"]),
                "selection_profile": manifest["selection_profile"],
                "source_commit": manifest["source_commit"],
                "items": [
                    {
                        "source_path": item["source_path"],
                        "sha256": item["sha256"],
                    }
                    for item in manifest["items"]
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
