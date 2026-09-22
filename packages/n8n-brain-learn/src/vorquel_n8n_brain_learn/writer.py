"""Persisting a batch as PENDING candidates.

This writer stops exactly where human review begins. It registers the source
and creates candidates; it never approves anything, and there is no parameter
that would let it. Approval is a separate, explicit act over ids a human has
already been shown (APPROVALS.md).

Everything goes through the Watch RPCs rather than direct table writes, so the
scope, classification and provenance rules enforced in 0023 apply to the Brain
exactly as they apply to Watch.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .model import LearnBatch

ENV_VAR = "VORQUEL_BRAIN_DATABASE_URL"


class WriterUnavailable(RuntimeError):
    """No usable connection. LEARN reports the batch instead of guessing."""


@dataclass(frozen=True)
class PersistResult:
    source_id: str
    source_version: int
    source_reused: bool
    created_candidate_ids: tuple[str, ...]
    reused_candidate_ids: tuple[str, ...]
    refused: int

    @property
    def is_idempotent_replay(self) -> bool:
        return not self.created_candidate_ids and bool(self.reused_candidate_ids)


@contextmanager
def _connection(dsn: str | None = None) -> Iterator[Any]:
    dsn = dsn or os.environ.get(ENV_VAR)
    if not dsn:
        raise WriterUnavailable(
            f"{ENV_VAR} nao definido. LEARN nao persiste sem o store."
        )
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - environment issue
        raise WriterUnavailable("psycopg nao instalado") from exc
    try:
        conn = psycopg.connect(dsn, autocommit=False)
    except Exception as exc:
        # The DSN itself must never reach a log line or a traceback.
        raise WriterUnavailable(f"conexao falhou: {type(exc).__name__}") from exc
    try:
        yield conn
    finally:
        conn.close()


def persist_batch(batch: LearnBatch, dsn: str | None = None) -> PersistResult:
    """Register the source and create every candidate as PENDING.

    Idempotent by construction: identical bytes reuse the source row, and an
    identical excerpt from the same place reuses the candidate. Re-learning a
    source therefore adds nothing and approves nothing.
    """
    source = batch.source

    with _connection(dsn) as conn:
        with conn.cursor() as cur:
            if source.is_externally_registered:
                # Watch owns this row. Confirm it exists and agrees about scope
                # rather than creating a second source for the same material.
                cur.execute(
                    """
                    select source_version, scope_type, scope_id
                    from public.sources
                    where source_id = %s and ingest_status = 'READY'
                    """,
                    (source.source_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise WriterUnavailable(
                        f"fonte {source.source_id} nao existe ou nao esta READY no Watch"
                    )
                version, scope_type, scope_id = row
                if (scope_type, scope_id) != (source.scope.scope_type, source.scope.scope_id):
                    raise WriterUnavailable(
                        "escopo pedido nao confere com o escopo da fonte registrada"
                    )
                source_version, reused = int(version), True
            else:
                cur.execute(
                    """
                    select source_id, source_version, reused
                    from public.register_external_source(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        source.source_id,
                        source.source_kind,
                        source.content_sha256,
                        source.byte_size,
                        source.detected_mime,
                        source.logical_key,
                        source.scope.scope_type,
                        source.scope.scope_id,
                        source.data_classification,
                        json.dumps(source.external_metadata, ensure_ascii=False),
                    ),
                )
                registered = cur.fetchone()
                if registered is None:
                    raise WriterUnavailable("register_external_source nao retornou nada")
                resolved_source_id, source_version, reused = registered
                # Identical bytes already registered under a different id: cite
                # the row that exists rather than the one we would have made.
                object.__setattr__(source, "existing_source_id", resolved_source_id)

            created: list[str] = []
            reused_candidates: list[str] = []
            for candidate in batch.candidates:
                cur.execute(
                    """
                    select candidate_id, reused
                    from public.create_knowledge_candidate_scoped(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        candidate.candidate_id,
                        source.source_id,
                        candidate.knowledge_type,
                        candidate.domain,
                        candidate.title,
                        candidate.summary,
                        candidate.epistemic_status,
                        candidate.content_hash,
                        source.scope.scope_type,
                        source.scope.scope_id,
                        candidate.data_classification,
                        json.dumps(candidate.provenance(), ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    raise WriterUnavailable("create_knowledge_candidate_scoped nao retornou nada")
                candidate_id, was_reused = row
                (reused_candidates if was_reused else created).append(candidate_id)

        conn.commit()

    return PersistResult(
        source_id=source.source_id,
        source_version=int(source_version),
        source_reused=bool(reused),
        created_candidate_ids=tuple(created),
        reused_candidate_ids=tuple(reused_candidates),
        refused=len(batch.refused),
    )
