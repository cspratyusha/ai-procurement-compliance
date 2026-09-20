"""Applies db/schema.sql (Phase 1 dev DDL) to a Postgres connection.

Not part of the SQL-centralisation rule in `db/queries.py` — this is
schema *creation*, not a query, and it's Phase 1 dev-only scaffolding: a
real migration tool is Teammate 1's call once their actual schema exists.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


def ensure_postgres_schema(conn: psycopg.Connection) -> None:
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
