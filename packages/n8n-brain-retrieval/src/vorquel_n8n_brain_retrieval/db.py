"""Read-only database access for retrieval.

Retrieval never writes. The session is opened read-only so a bug cannot become a
mutation, and the connection string is only ever read from the environment.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

ENV_VAR = "VORQUEL_BRAIN_DATABASE_URL"


class DatabaseUnavailable(RuntimeError):
    """No usable connection. Callers degrade rather than guess."""


@contextmanager
def read_only_connection(dsn: str | None = None) -> Iterator[Any]:
    dsn = dsn or os.environ.get(ENV_VAR)
    if not dsn:
        raise DatabaseUnavailable(
            f"{ENV_VAR} nao definido. Retrieval nao inventa conteudo sem o store."
        )
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - environment issue
        raise DatabaseUnavailable("psycopg nao instalado") from exc

    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as exc:
        raise DatabaseUnavailable(f"conexao falhou: {type(exc).__name__}") from exc
    try:
        with conn.cursor() as cur:
            cur.execute("set session characteristics as transaction read only")
        yield conn
    finally:
        conn.close()


def fetch_all(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def column_exists(conn: Any, schema: str, table: str, column: str) -> bool:
    rows = fetch_all(
        conn,
        """
        select 1
        from information_schema.columns
        where table_schema = %s and table_name = %s and column_name = %s
        """,
        (schema, table, column),
    )
    return bool(rows)


def function_exists(conn: Any, schema: str, name: str) -> bool:
    rows = fetch_all(
        conn,
        """
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = %s and p.proname = %s
        """,
        (schema, name),
    )
    return bool(rows)
