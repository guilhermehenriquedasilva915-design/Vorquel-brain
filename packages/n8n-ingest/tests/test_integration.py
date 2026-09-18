from __future__ import annotations

import json
import os

import psycopg
import pytest

from vorquel_n8n_ingest.core import compile_manifest_items, plan_manifest
from vorquel_n8n_knowledge_writer.writer import write_prepared_records_batch

pytestmark = pytest.mark.skipif(
    not os.environ.get("N8N_BRAIN_TEST_DATABASE_URL"),
    reason="integration database is not configured",
)

REPO = "JustInCache/n8n-workflows"
COMMIT = "5a7864987c22930521382b597873b713cc830dac"


def _workflow(name):
    return {
        "name": name,
        "nodes": [
            {
                "name": "Manual",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "parameters": {},
            }
        ],
        "connections": {},
    }


def test_controlled_batch_is_atomic_and_idempotent(tmp_path):
    for index in range(2):
        path = tmp_path / "workflows" / f"{index}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_workflow(f"Fixture {index}")), encoding="utf-8")

    manifest = plan_manifest(
        tmp_path,
        source_repo=REPO,
        source_commit=COMMIT,
        analyzer_version="0.1.0",
        count=2,
    )
    compiled = compile_manifest_items(tmp_path, manifest)

    with psycopg.connect(os.environ["N8N_BRAIN_TEST_DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                truncate table
                  n8n_brain.knowledge_items,
                  n8n_brain.workflow_analyses,
                  n8n_brain.source_snapshots
                cascade
                """
            )
        connection.commit()

        first = write_prepared_records_batch(
            connection,
            [item.records for item in compiled],
        )
        second = write_prepared_records_batch(
            connection,
            [item.records for item in compiled],
        )

        assert all(result.source_created for result in first)
        assert all(result.analysis_created for result in first)
        assert all(result.knowledge_created for result in first)
        assert not any(result.source_created for result in second)
        assert not any(result.analysis_created for result in second)
        assert not any(result.knowledge_created for result in second)

        with connection.cursor() as cursor:
            cursor.execute("select count(*) from n8n_brain.source_snapshots")
            assert cursor.fetchone()[0] == 2
            cursor.execute("select count(*) from n8n_brain.workflow_analyses")
            assert cursor.fetchone()[0] == 2
            cursor.execute("select count(*) from n8n_brain.knowledge_items")
            assert cursor.fetchone()[0] == 2
