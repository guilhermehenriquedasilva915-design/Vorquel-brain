from __future__ import annotations

import json
import os
import psycopg
import pytest
from vorquel_n8n_controlled_ingestion.ingest import ingest_manifest
from vorquel_n8n_controlled_ingestion.planner import build_manifest

DATABASE_URL = os.environ.get("N8N_BRAIN_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="integration database not configured")


def _safe_workflow(name: str) -> dict:
    return {
        "name": name,
        "nodes": [
            {
                "name": "No Op",
                "type": "n8n-nodes-base.noOp",
                "typeVersion": 1,
                "parameters": {},
            }
        ],
        "connections": {},
    }


def test_manifest_persistence_is_atomic_and_idempotent(tmp_path):
    assert DATABASE_URL is not None
    for index in range(4):
        (tmp_path / f"{index:02d}.json").write_text(
            json.dumps(_safe_workflow(f"Safe {index}")),
            encoding="utf-8",
        )

    manifest = build_manifest(
        tmp_path,
        source_repo="integration/n8n-workflows",
        source_commit="c" * 40,
        analyzer_version="0.1.0",
        max_items=4,
    )

    with psycopg.connect(DATABASE_URL) as connection:
        first = ingest_manifest(tmp_path, manifest, connection=connection, persist=True)
        second = ingest_manifest(tmp_path, manifest, connection=connection, persist=True)

        with connection.cursor() as cursor:
            cursor.execute("select count(*) from n8n_brain.source_snapshots")
            source_count = cursor.fetchone()[0]
            cursor.execute("select count(*) from n8n_brain.workflow_analyses")
            analysis_count = cursor.fetchone()[0]
            cursor.execute("select count(*) from n8n_brain.knowledge_items")
            knowledge_count = cursor.fetchone()[0]

    assert first["item_count"] == 4
    assert all(item["created"]["knowledge"] for item in first["items"])
    assert all(not item["created"]["knowledge"] for item in second["items"])
    assert (source_count, analysis_count, knowledge_count) == (4, 4, 4)
