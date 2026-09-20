"""A fake psycopg-shaped connection.

These tests must be able to prove the isolation rules without a live database,
because the rule that matters most — one client never seeing another's
knowledge — has to hold on a laptop, in CI and in front of a customer alike.
"""

from __future__ import annotations

from typing import Any


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn
        self.description: list[tuple[str]] | None = None
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = ()) -> None:
        self._conn.executed.append((" ".join(sql.split()), params))
        cols, rows = self._conn.respond(sql, params)
        self.description = [(c,) for c in cols] if cols else None
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class FakeConn:
    """Responds to the handful of shapes retrieval actually issues."""

    def __init__(
        self,
        *,
        columns: set[tuple[str, str, str]] | None = None,
        functions: set[tuple[str, str]] | None = None,
        knowledge_rows: list[dict[str, Any]] | None = None,
        provenance_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.columns = columns if columns is not None else set()
        self.functions = functions if functions is not None else set()
        self.knowledge_rows = knowledge_rows or []
        self.provenance_rows = provenance_rows or []
        self.executed: list[tuple[str, Any]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def respond(self, sql: str, params: Any) -> tuple[list[str], list[tuple[Any, ...]]]:
        flat = " ".join(sql.split()).lower()

        if "information_schema.columns" in flat:
            schema, table, column = params
            hit = (schema, table, column) in self.columns
            return (["?column?"], [(1,)] if hit else [])

        if "pg_proc" in flat:
            schema, name = params
            hit = (schema, name) in self.functions
            return (["?column?"], [(1,)] if hit else [])

        if "knowledge_sources" in flat:
            return self._rows_as(self.provenance_rows)

        if "knowledge_items" in flat or "search_knowledge_items_scoped" in flat:
            return self._rows_as(self.knowledge_rows)

        # operational_experiences, n8n_brain.knowledge_items and anything else
        # this test double does not model.
        return ([], [])

    @staticmethod
    def _rows_as(rows: list[dict[str, Any]]) -> tuple[list[str], list[tuple[Any, ...]]]:
        if not rows:
            return ([], [])
        cols = list(rows[0].keys())
        return (cols, [tuple(r.get(c) for c in cols) for r in rows])
