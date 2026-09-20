"""PostgreSQL 访问层（psycopg 3，dict 行）。"""
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from . import config


@contextmanager
def get_conn():
    conn = psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
