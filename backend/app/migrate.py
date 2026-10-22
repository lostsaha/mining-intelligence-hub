"""按文件名顺序执行 backend/sql/*.sql，并记录到 mining.schema_migrations。

用法（在 backend 目录）：
    python -m app.migrate
    python -m app.migrate --dry-run

说明：迁移文件内部使用简单查询协议执行，可包含 DO $$...$$ 等多语句块；
每个文件在独立事务中执行，失败即回滚且不记录版本。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg import pq
from psycopg.rows import dict_row

from . import config

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
BOOTSTRAP = """
CREATE SCHEMA IF NOT EXISTS mining;
CREATE TABLE IF NOT EXISTS mining.schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _iter_files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"), key=lambda p: p.name)


def _applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM mining.schema_migrations")
        return {r["version"] for r in cur.fetchall()}


def _run_sql(conn: psycopg.Connection, sql: str) -> None:
    """使用 libpq 简单查询协议执行，支持多语句与 DO 块。"""
    result = conn.pgconn.exec_(sql.encode("utf-8"))
    if result.status not in (pq.ExecStatus.COMMAND_OK, pq.ExecStatus.TUPLES_OK):
        message = conn.pgconn.error_message.decode("utf-8", "replace")
        raise RuntimeError(message or f"SQL failed with status {result.status}")


def migrate(dry_run: bool = False) -> list[str]:
    files = _iter_files()
    if not files:
        raise RuntimeError(f"no SQL files found in {SQL_DIR}")

    applied_now: list[str] = []
    with psycopg.connect(
        config.DATABASE_URL,
        row_factory=dict_row,
        autocommit=False,
        connect_timeout=config.DB_CONNECT_TIMEOUT,
        application_name="mining-migrate",
    ) as conn:
        _run_sql(conn, BOOTSTRAP)
        conn.commit()

        applied = _applied(conn)
        for path in files:
            version = path.name
            if version in applied:
                print(f"[skip] {version}")
                continue
            print(f"[apply] {version}")
            if dry_run:
                applied_now.append(version)
                continue
            try:
                _run_sql(conn, path.read_text(encoding="utf-8"))
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO mining.schema_migrations (version) VALUES (%s) "
                        "ON CONFLICT (version) DO NOTHING",
                        (version,),
                    )
                conn.commit()
                applied_now.append(version)
            except Exception:
                conn.rollback()
                print(f"[fail] {version}", file=sys.stderr)
                raise

    if dry_run:
        print(f"dry-run: {len(applied_now)} migration(s) pending")
    else:
        print(f"done: {len(applied_now)} migration(s) applied")
    return applied_now


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mining platform SQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="only list pending migrations")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
