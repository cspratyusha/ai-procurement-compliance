"""Database connection pool for the API layer."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://procurement:procurement@localhost:55432/procurement",
)


@contextmanager
def get_connection() -> Generator[psycopg.Connection, None, None]:
    """Yield a short-lived connection with dict-row factory."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn
