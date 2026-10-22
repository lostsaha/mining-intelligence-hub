"""PostgreSQL 访问层（psycopg 3，dict 行）。

默认每条语句使用独立连接（autocommit），便于脚本快速调用；
需要原子写入时用 ``with db.transaction():``，块内的 ``query/execute``
会自动复用同一连接并统一提交/回滚。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from . import config

_ambient_conn: ContextVar[psycopg.Connection | None] = ContextVar(
    "mining_ambient_conn", default=None
)


def _connect(autocommit: bool) -> psycopg.Connection:
    return psycopg.connect(
        config.DATABASE_URL,
        row_factory=dict_row,
        autocommit=autocommit,
        connect_timeout=config.DB_CONNECT_TIMEOUT,
        application_name="mining-platform",
    )


@contextmanager
def get_conn(autocommit: bool = True) -> Iterator[psycopg.Connection]:
    """获取连接。若当前处于 transaction() 中，复用环境连接且不关闭。"""
    ambient = _ambient_conn.get()
    if ambient is not None:
        yield ambient
        return
    conn = _connect(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """原子事务上下文；嵌套调用复用外层事务。"""
    ambient = _ambient_conn.get()
    if ambient is not None:
        yield ambient
        return
    conn = _connect(autocommit=False)
    token = _ambient_conn.set(conn)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        _ambient_conn.reset(token)
        conn.close()


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else []


def query_one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def atomic(func):
    """装饰器：把整个函数包进一个事务（函数内 query/execute 自动复用连接）。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with transaction():
            return func(*args, **kwargs)

    return wrapper


def execute(sql: str, params: tuple | list = ()) -> int:
    """执行写入，返回受影响行数。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_returning(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if cur.description else None


def ping() -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        row = cur.fetchone()
        return bool(row and row.get("ok") == 1)
