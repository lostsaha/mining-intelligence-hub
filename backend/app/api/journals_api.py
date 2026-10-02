"""期刊排名 API：按语料聚合期刊的论文量/被引/篇均被引，支持检索与排序。"""
from __future__ import annotations

from fastapi import Query

from .. import db

SORTS = {
    "citations": "SUM(w.cited_by_count) DESC",
    "papers": "COUNT(*) DESC",
    "avg": "AVG(w.cited_by_count) DESC",
    "name": "journal",
}


def journals(
    q: str | None = None,
    sort: str = "citations",
    min_papers: int = 5,
    limit: int = Query(60, le=200),
) -> dict:
    where = ["w.source_name IS NOT NULL", "w.source_name <> ''"]
    params: list = []
    if q:
        where.append("w.source_name ILIKE %s")
        params.append(f"%{q}%")

    order = SORTS.get(sort, SORTS["citations"])
    rows = db.query(
        f"""
        SELECT w.source_name AS journal,
               COUNT(*) AS papers,
               COUNT(*) FILTER (
                   WHERE EXISTS (SELECT 1 FROM mining.work_topic wt WHERE wt.work_id = w.work_id)
               ) AS mining_papers,
               COALESCE(SUM(w.cited_by_count), 0) AS total_citations,
               COALESCE(ROUND(AVG(w.cited_by_count)::numeric, 1), 0) AS avg_citations,
               MIN(w.publication_year) AS since_year,
               MAX(w.publication_year) AS to_year
        FROM mining.works w
        WHERE {" AND ".join(where)}
        GROUP BY w.source_name
        HAVING COUNT(*) >= %s
           AND COUNT(*) FILTER (
               WHERE EXISTS (SELECT 1 FROM mining.work_topic wt WHERE wt.work_id = w.work_id)
           ) >= 5
        ORDER BY {order}
        LIMIT %s
        """,
        (*params, min_papers, limit),
    )
    total = db.query_one(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT w.source_name
            FROM mining.works w
            WHERE {" AND ".join(where)}
            GROUP BY w.source_name
            HAVING COUNT(*) >= %s
               AND COUNT(*) FILTER (
                   WHERE EXISTS (SELECT 1 FROM mining.work_topic wt WHERE wt.work_id = w.work_id)
               ) >= 5
        ) t
        """,
        (*params, min_papers),
    )
    return {"total": total["n"] if total else 0, "journals": rows}
