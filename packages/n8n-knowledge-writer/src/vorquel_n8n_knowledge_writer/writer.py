from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from .validation import PreparedRecords, prepare_records

_WRITER_ROLE = "n8n_brain_writer"


class ImmutableDriftError(RuntimeError):
    """Raised when an immutable version key already exists with different content."""


@dataclass(frozen=True)
class WriteResult:
    source_id: str
    analysis_id: str
    knowledge_id: str
    source_created: bool
    analysis_created: bool
    knowledge_created: bool


def _row_dict(cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column.name for column in cursor.description]
    return dict(zip(columns, row, strict=True))


def _source(cursor, record: dict[str, Any]) -> tuple[str, bool]:
    cursor.execute(
        """
        insert into n8n_brain.source_snapshots (
          source_repo,
          source_commit,
          source_path,
          content_sha256,
          source_kind,
          trust_level
        ) values (%s, %s, %s, %s, %s, %s)
        on conflict (
          source_repo,
          source_commit,
          source_path,
          content_sha256
        ) do nothing
        returning id
        """,
        (
            record["source_repo"],
            record["source_commit"],
            record["source_path"],
            record["content_sha256"],
            record["source_kind"],
            record["trust_level"],
        ),
    )
    inserted = cursor.fetchone()
    if inserted is not None:
        return str(inserted[0]), True

    cursor.execute(
        """
        select id, source_kind, trust_level
        from n8n_brain.source_snapshots
        where source_repo = %s
          and source_commit = %s
          and source_path = %s
          and content_sha256 = %s
        """,
        (
            record["source_repo"],
            record["source_commit"],
            record["source_path"],
            record["content_sha256"],
        ),
    )
    existing = _row_dict(cursor)
    if existing is None:
        raise ImmutableDriftError("source snapshot conflict could not be resolved")
    if (
        existing["source_kind"] != record["source_kind"]
        or existing["trust_level"] != record["trust_level"]
    ):
        raise ImmutableDriftError("source snapshot immutable fields have drifted")
    return str(existing["id"]), False


def _analysis(
    cursor,
    *,
    source_id: str,
    record: dict[str, Any],
) -> tuple[str, bool]:
    cursor.execute(
        """
        insert into n8n_brain.workflow_analyses (
          source_id,
          analyzer_version,
          risk_decision,
          max_severity,
          findings
        ) values (%s, %s, %s, %s, %s)
        on conflict (source_id, analyzer_version) do nothing
        returning id
        """,
        (
            source_id,
            record["analyzer_version"],
            record["risk_decision"],
            record["max_severity"],
            Jsonb(record["findings"]),
        ),
    )
    inserted = cursor.fetchone()
    if inserted is not None:
        return str(inserted[0]), True

    cursor.execute(
        """
        select id, risk_decision, max_severity, findings
        from n8n_brain.workflow_analyses
        where source_id = %s
          and analyzer_version = %s
        """,
        (source_id, record["analyzer_version"]),
    )
    existing = _row_dict(cursor)
    if existing is None:
        raise ImmutableDriftError("analysis conflict could not be resolved")

    expected = {
        "risk_decision": record["risk_decision"],
        "max_severity": record["max_severity"],
        "findings": record["findings"],
    }
    observed = {
        "risk_decision": existing["risk_decision"],
        "max_severity": existing["max_severity"],
        "findings": existing["findings"],
    }
    if observed != expected:
        raise ImmutableDriftError(
            "analysis content changed without an analyzer version change"
        )
    return str(existing["id"]), False


def _knowledge(
    cursor,
    *,
    analysis_id: str,
    record: dict[str, Any],
) -> tuple[str, bool]:
    cursor.execute(
        """
        insert into n8n_brain.knowledge_items (
          analysis_id,
          compiler_schema_version,
          source_content_trust,
          knowledge_role,
          learning_scope,
          structure,
          untrusted_text,
          executable_metadata,
          security_findings,
          implementation_reference_allowed,
          vorquel_validated
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (analysis_id, compiler_schema_version) do nothing
        returning id
        """,
        (
            analysis_id,
            record["compiler_schema_version"],
            record["source_content_trust"],
            record["knowledge_role"],
            record["learning_scope"],
            Jsonb(record["structure"]),
            Jsonb(record["untrusted_text"]),
            Jsonb(record["executable_metadata"]),
            Jsonb(record["security_findings"]),
            record["implementation_reference_allowed"],
            record["vorquel_validated"],
        ),
    )
    inserted = cursor.fetchone()
    if inserted is not None:
        return str(inserted[0]), True

    cursor.execute(
        """
        select
          id,
          source_content_trust,
          knowledge_role,
          learning_scope,
          structure,
          untrusted_text,
          executable_metadata,
          security_findings,
          implementation_reference_allowed,
          vorquel_validated
        from n8n_brain.knowledge_items
        where analysis_id = %s
          and compiler_schema_version = %s
        """,
        (analysis_id, record["compiler_schema_version"]),
    )
    existing = _row_dict(cursor)
    if existing is None:
        raise ImmutableDriftError("knowledge item conflict could not be resolved")

    expected = {
        "source_content_trust": record["source_content_trust"],
        "knowledge_role": record["knowledge_role"],
        "learning_scope": record["learning_scope"],
        "structure": record["structure"],
        "untrusted_text": record["untrusted_text"],
        "executable_metadata": record["executable_metadata"],
        "security_findings": record["security_findings"],
        "implementation_reference_allowed": record[
            "implementation_reference_allowed"
        ],
        "vorquel_validated": record["vorquel_validated"],
    }
    observed = {
        key: existing[key]
        for key in expected
    }
    if observed != expected:
        raise ImmutableDriftError(
            "knowledge content changed without a compiler schema version change"
        )
    return str(existing["id"]), False


def write_prepared_records(
    connection: Connection[Any],
    records: PreparedRecords,
) -> WriteResult:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("set local role n8n_brain_writer")
        cursor.execute("set local statement_timeout = '5s'")
        cursor.execute("set local lock_timeout = '2s'")

        source_id, source_created = _source(cursor, records.source)
        analysis_id, analysis_created = _analysis(
            cursor,
            source_id=source_id,
            record=records.analysis,
        )
        knowledge_id, knowledge_created = _knowledge(
            cursor,
            analysis_id=analysis_id,
            record=records.knowledge,
        )

    return WriteResult(
        source_id=source_id,
        analysis_id=analysis_id,
        knowledge_id=knowledge_id,
        source_created=source_created,
        analysis_created=analysis_created,
        knowledge_created=knowledge_created,
    )


def write_knowledge_item(
    connection: Connection[Any],
    item: dict[str, Any],
    *,
    analyzer_version: str,
) -> WriteResult:
    records = prepare_records(item, analyzer_version=analyzer_version)
    return write_prepared_records(connection, records)
