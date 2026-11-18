"""Database access. Every tenant-scoped query runs inside tenant_tx(), which sets the RLS
context with SET LOCAL so it can never leak to another request on a pooled connection."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.config import settings

_dsn_override: str | None = None


def set_dsn(dsn: str) -> None:
    """Test hook: point the app at a disposable database."""
    global _dsn_override
    _dsn_override = dsn


def _connect() -> psycopg.Connection:
    return psycopg.connect(_dsn_override or settings.database_url, row_factory=dict_row, autocommit=False)


@contextmanager
def global_tx() -> Iterator[psycopg.Cursor]:
    """Transaction with no tenant context (identity tables only; tenant tables return nothing)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            yield cur
        conn.commit()


@contextmanager
def tenant_tx(tenant_id: UUID | str) -> Iterator[psycopg.Cursor]:
    if not tenant_id:
        raise PermissionError("tenant context required")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('aav.tenant_id', %s, true)", (str(UUID(str(tenant_id))),))
            yield cur
        conn.commit()
