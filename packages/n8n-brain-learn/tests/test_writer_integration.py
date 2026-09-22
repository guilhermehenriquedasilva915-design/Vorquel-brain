"""The writer against a real database, when one is offered.

These tests need the Vorquel Watch knowledge schema (migrations 0014-0023),
which lives in the Vorquel-watch repository. This repository's CI cannot check
that one out, so the SQL-level proof of the LEARN -> review -> retrieval chain
runs there, in the `knowledge-migrations` job.

What runs here is the Python writer against that schema, skipped unless
N8N_BRAIN_TEST_DATABASE_URL points at a database that already has it. The skip
is deliberate and reported: a test that silently passed without a database
would claim persistence works when nothing was persisted.
"""

from __future__ import annotations

import os

import pytest

from vorquel_n8n_brain_learn.adapters import learn_message
from vorquel_n8n_brain_learn.writer import WriterUnavailable, persist_batch

DSN = os.environ.get("N8N_BRAIN_TEST_DATABASE_URL")

LONG = (
    "O no HTTP Request precisa de retryOnFail com maxTries limitado, "
    "porque um retry sem teto gira ate estourar a fila de execucao."
)


def _has_knowledge_schema() -> bool:
    if not DSN:
        return False
    try:
        import psycopg
    except ModuleNotFoundError:  # pragma: no cover - environment issue
        return False
    try:
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "select to_regprocedure('public.create_knowledge_candidate_scoped"
                "(text,text,text,text,text,text,text,text,text,text,text,jsonb)')"
            )
            return cur.fetchone()[0] is not None
    except Exception:  # pragma: no cover - environment issue
        return False


requires_schema = pytest.mark.skipif(
    not _has_knowledge_schema(),
    reason="needs N8N_BRAIN_TEST_DATABASE_URL with the vorquel_knowledge schema applied",
)


def test_persisting_without_a_dsn_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VORQUEL_BRAIN_DATABASE_URL", raising=False)
    batch = learn_message(LONG, "GLOBAL_VORQUEL")

    with pytest.raises(WriterUnavailable, match="VORQUEL_BRAIN_DATABASE_URL"):
        persist_batch(batch)


def test_a_bad_dsn_never_appears_in_the_error() -> None:
    batch = learn_message(LONG, "GLOBAL_VORQUEL")
    secret_dsn = "postgresql://user:hunter2@nonexistent.invalid:5432/db"

    with pytest.raises(WriterUnavailable) as caught:
        persist_batch(batch, dsn=secret_dsn)

    assert "hunter2" not in str(caught.value)
    assert "nonexistent.invalid" not in str(caught.value)


@requires_schema
def test_learning_persists_pending_candidates_and_nothing_else() -> None:
    batch = learn_message(LONG, "CLIENT:acme", "CLIENT_CONFIDENTIAL")

    result = persist_batch(batch, dsn=DSN)

    assert result.created_candidate_ids
    import psycopg

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "select status, scope_type, scope_id from vorquel_knowledge.knowledge_candidates "
            "where candidate_id = any(%s)",
            (list(result.created_candidate_ids),),
        )
        rows = cur.fetchall()
        assert rows
        assert all(row == ("PENDING", "CLIENT", "acme") for row in rows)

        # Nothing became knowledge: approval is a separate, human act.
        cur.execute(
            "select count(*) from vorquel_knowledge.knowledge_items "
            "where candidate_id = any(%s)",
            (list(result.created_candidate_ids),),
        )
        assert cur.fetchone()[0] == 0


@requires_schema
def test_relearning_the_same_source_is_a_no_op() -> None:
    batch = learn_message(LONG + " Idempotente.", "GLOBAL_VORQUEL")

    first = persist_batch(batch, dsn=DSN)
    second = persist_batch(batch, dsn=DSN)

    assert first.created_candidate_ids
    assert second.created_candidate_ids == ()
    assert set(second.reused_candidate_ids) == set(first.created_candidate_ids)
    assert second.is_idempotent_replay
    assert second.source_reused
