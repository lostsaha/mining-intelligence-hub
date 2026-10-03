"""embedding 回填：works 摘要 / document_chunks / work_chunks → pgvector。

前置：
  1) 数据库镜像已换 pgvector/pgvector:pg16，sql/010_embeddings.sql 已执行
  2) backend/.env 配置 EMBEDDINGS_BASE_URL / EMBEDDINGS_API_KEY / EMBEDDINGS_MODEL
用法：
  python -m app.documents.embed_backfill --target works    [--limit N]
  python -m app.documents.embed_backfill --target chunks   [--limit N]   # 书籍分段
  python -m app.documents.embed_backfill --target work_chunks [--limit N]
  python -m app.documents.embed_backfill --index          # 回填完后建 HNSW 索引
行为：只补 embedding IS NULL 的行；每批 64 条，失败重试 3 次；可随时中断重跑（幂等）。
"""
from __future__ import annotations

import argparse
import sys
import time

from .. import db, emb

BATCH = 64
_SLEEP = 0.2  # 批间限速

_TARGETS = {
    # 表名: (主键, 文本表达式, 已有文本非空的过滤)
    "works": ("work_id", "coalesce(abstract, '')", "abstract IS NOT NULL AND abstract <> ''"),
    "chunks": ("chunk_id", "content", "content IS NOT NULL AND content <> ''"),
    "work_chunks": ("chunk_id", "content", "content IS NOT NULL AND content <> ''"),
}
_TABLE_OF = {"works": "works", "chunks": "document_chunks", "work_chunks": "work_chunks"}


def _pending(table: str) -> int:
    return db.query_one(f"SELECT COUNT(*) AS n FROM mining.{table} WHERE embedding IS NULL")["n"]


def _fetch_batch(table: str, pk: str, text_expr: str, flt: str) -> list[dict]:
    return db.query(
        f"SELECT {pk} AS id, {text_expr} AS text FROM mining.{table} "
        f"WHERE embedding IS NULL AND {flt} ORDER BY {pk} LIMIT %s",
        (BATCH,),
    )


def backfill(target: str, limit: int | None = None) -> None:
    table = _TABLE_OF[target]
    pk, text_expr, flt = _TARGETS[target]
    done = 0
    while True:
        if limit is not None and done >= limit:
            break
        rows = _fetch_batch(table, pk, text_expr, flt)
        if not rows:
            break
        if limit is not None:
            rows = rows[: limit - done]
        vecs = emb.embed([r["text"] for r in rows])
        with db.get_conn() as conn, conn.cursor() as cur:
            for r, v in zip(rows, vecs):
                vec_lit = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
                cur.execute(
                    f"UPDATE mining.{table} SET embedding = %s::vector WHERE {pk} = %s",
                    (vec_lit, r["id"]),
                )
        done += len(rows)
        remain = _pending(table)
        print(f"[{target}] 已回填 {done}，剩余 {remain}", flush=True)
        time.sleep(_SLEEP)
    print(f"[{target}] 回填结束，共 {done} 条")


def create_index() -> None:
    for table in _TABLE_OF.values():
        n = db.query_one(f"SELECT COUNT(*) AS n FROM mining.{table} WHERE embedding IS NOT NULL")["n"]
        if n == 0:
            print(f"[skip] {table}: 无向量")
            continue
        t0 = time.time()
        db.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_emb ON mining.{table} "
            f"USING hnsw (embedding vector_cosine_ops)"
        )
        print(f"[index] {table}: {n} 条向量，HNSW 建好（{time.time() - t0:.0f}s）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=list(_TARGETS), help="回填目标")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--index", action="store_true", help="建 HNSW 索引")
    args = ap.parse_args()

    if args.index:
        create_index()
        sys.exit(0)
    if not args.target:
        ap.error("需要 --target 或 --index")
    if not emb.EMBEDDINGS_ENABLED:
        print("Embeddings 未配置：请在 backend/.env 设置 EMBEDDINGS_BASE_URL/API_KEY/MODEL")
        sys.exit(1)
    backfill(args.target, args.limit)
