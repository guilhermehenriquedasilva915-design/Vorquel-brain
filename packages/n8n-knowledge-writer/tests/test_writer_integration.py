from __future__ import annotations

import copy
import os

import psycopg
import pytest

from vorquel_n8n_knowledge_writer.validation import prepare_records
from vorquel_n8n_knowledge_writer.writer import (
    ImmutableDriftError,
    write_prepared_records,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("N8N_BRAIN_TEST_DATABASE_URL"),
    reason="integration database is not configured",
)


def connect():
    return psycopg.connect(os.environ["N8N_BRAIN_TEST_DATABASE_URL"])


def truncate_tables(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            truncate table
              n8n_brain.knowledge_items,
              n8n_brain.workflow_analyses,
              n8n_brain.source_snapshots
            restart identity cascade
            """
        )
    connection.commit()


def test_write_is_idempotent(knowledge_item):
    records = prepare_records(knowledge_item, analyzer_version="0.1")

    with connect() as connection:
        truncate_tables(connection)
        first = write_prepared_records(connection, records)
        second = write_prepared_records(connection, records)

        assert first.source_created is True
        assert first.analysis_created is True
        assert first.knowledge_created is True
        assert second.source_created is False
        assert second.analysis_created is False
        assert second.knowledge_created is False
        assert first.source_id == second.source_id
        assert first.analysis_id == second.analysis_id
        assert first.knowledge_id == second.knowledge_id

        with connection.cursor() as cursor:
            cursor.execute("select count(*) from n8n_brain.source_snapshots")
            assert cursor.fetchone()[0] == 1
            cursor.execute("select count(*) from n8n_brain.workflow_analyses")
            assert cursor.fetchone()[0] == 1
            cursor.execute("select count(*) from n8n_brain.knowledge_items")
            assert cursor.fetchone()[0] == 1


def test_same_compiler_version_with_changed_structure_fails_closed(knowledge_item):
    first_records = prepare_records(knowledge_item, analyzer_version="0.1")
    changed = copy.deepcopy(knowledge_item)
    changed["workflow"]["name_untrusted"] = "Changed without version bump"
    changed_records = prepare_records(changed, analyzer_version="0.1")

    with connect() as connection:
        truncate_tables(connection)
        write_prepared_records(connection, first_records)

        with pytest.raises(ImmutableDriftError):
            write_prepared_records(connection, changed_records)


def test_same_analyzer_version_with_changed_risk_fails_closed(knowledge_item):
    first_records = prepare_records(knowledge_item, analyzer_version="0.1")
    changed = copy.deepcopy(knowledge_item)
    changed["admission"].update(
        {
            "risk_decision": "BLOCKED",
            "max_severity": "CRITICAL",
            "knowledge_role": "SECURITY_EXAMPLE",
            "learning_scope": "security_only",
            "structure_reference_allowed": False,
        }
    )
    changed_records = prepare_records(changed, analyzer_version="0.1")

    with connect() as connection:
        truncate_tables(connection)
        write_prepared_records(connection, first_records)

        with pytest.raises(ImmutableDriftError):
            write_prepared_records(connection, changed_records)


def test_database_writer_role_is_append_only():
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            select
              has_schema_privilege('n8n_brain_writer', 'n8n_brain', 'USAGE'),
              has_table_privilege(
                'n8n_brain_writer',
                'n8n_brain.source_snapshots',
                'SELECT'
              ),
              has_table_privilege(
                'n8n_brain_writer',
                'n8n_brain.source_snapshots',
                'INSERT'
              ),
              has_table_privilege(
                'n8n_brain_writer',
                'n8n_brain.source_snapshots',
                'UPDATE'
              ),
              has_table_privilege(
                'n8n_brain_writer',
                'n8n_brain.source_snapshots',
                'DELETE'
              ),
              (
                select rolbypassrls
                from pg_roles
                where rolname = 'n8n_brain_writer'
              )
            """
        )
        (
            schema_usage,
            can_select,
            can_insert,
            can_update,
            can_delete,
            bypass_rls,
        ) = cursor.fetchone()

        assert schema_usage is True
        assert can_select is True
        assert can_insert is True
        assert can_update is False
        assert can_delete is False
        assert bypass_rls is False
