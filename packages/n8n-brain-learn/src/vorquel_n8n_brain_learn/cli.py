"""`vorquel-brain-learn` -- read a source, show the batch, optionally persist it.

Dry run is the default. Persisting creates PENDING candidates and nothing else:
this command cannot approve, and adding a flag that did would move the review
gate into a script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import learn_document, learn_message, learn_n8n_workflow
from .model import LearnBatch, LearnError
from .writer import WriterUnavailable, persist_batch


def _batch_as_json(batch: LearnBatch) -> dict[str, object]:
    return {
        "source": {
            "source_id": batch.source.source_id,
            "source_kind": batch.source.source_kind,
            "content_sha256": batch.source.content_sha256,
            "logical_key": batch.source.logical_key,
            "scope": str(batch.source.scope),
            "data_classification": batch.source.data_classification,
        },
        "candidate_count": len(batch.candidates),
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "title": candidate.title,
                "knowledge_type": candidate.knowledge_type,
                "epistemic_status": candidate.epistemic_status,
                "data_classification": candidate.data_classification,
                "locator_kind": candidate.locator_kind,
                "locator": candidate.locator,
                "redactions": list(candidate.redactions),
                "instruction_attempts": list(candidate.instruction_attempts),
            }
            for candidate in batch.candidates
        ],
        "refused": [
            {"rule": item.rule, "reason": item.reason, "locator_kind": item.locator_kind}
            for item in batch.refused
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vorquel-brain-learn",
        description="Transforma uma fonte em candidatos PENDENTES, com escopo e citacao.",
    )
    parser.add_argument("--scope", required=True, help="GLOBAL_VORQUEL ou CLIENT:acme")
    parser.add_argument(
        "--classification",
        default="INTERNAL",
        choices=["PUBLIC", "INTERNAL", "CLIENT_CONFIDENTIAL", "PII"],
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--file", help="txt, md, json, pdf ou docx")
    source_group.add_argument("--workflow", help="workflow n8n (passa por Analyzer + Compiler)")
    source_group.add_argument("--message-file", help="arquivo com o texto fornecido pelo operador")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="cria os candidatos como PENDING. Nunca aprova nada.",
    )
    parser.add_argument("--json", action="store_true", help="saida legivel por maquina")
    args = parser.parse_args(argv)

    try:
        if args.workflow:
            batch = learn_n8n_workflow(args.workflow, args.scope, args.classification)
        elif args.file:
            batch = learn_document(args.file, args.scope, args.classification)
        else:
            text = Path(args.message_file).read_text(encoding="utf-8")
            batch = learn_message(text, args.scope, args.classification)
    except LearnError as exc:
        print(f"LEARN recusou a fonte: {exc}", file=sys.stderr)
        return 2

    payload = _batch_as_json(batch)

    if args.persist:
        try:
            result = persist_batch(batch)
        except WriterUnavailable as exc:
            print(f"nao foi possivel persistir: {exc}", file=sys.stderr)
            return 3
        payload["persisted"] = {
            "source_id": result.source_id,
            "source_version": result.source_version,
            "source_reused": result.source_reused,
            "created": list(result.created_candidate_ids),
            "reused": list(result.reused_candidate_ids),
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for line in batch.summary_lines():
            print(line)
        if args.persist:
            persisted = payload["persisted"]
            print(
                f"persistido: {len(persisted['created'])} novo(s), "  # type: ignore[index]
                f"{len(persisted['reused'])} ja existia(m)"  # type: ignore[index]
            )
        print("\nNada disso e conhecimento ainda. Aprovacao humana e um passo separado.")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
