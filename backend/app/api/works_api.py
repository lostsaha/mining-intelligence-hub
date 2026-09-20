"""文献检索 API：语料内论文搜索（标题/摘要），含主题归属与作者。"""
from __future__ import annotations

from fastapi import Query

from .. import db


def search_works(
    q: str | None = None,
    topic: str | None = None,
    year_from: int | None = None,
    sort: str = "citations",
    limit: int = Query(30, le=100),
    offset: int = 0,
) -> dict:
    where: list[str] = []
    params: list = []
    if q:
        where.append("(w.title ILIKE %s OR w.abstract ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if topic:
        where.append(
            "EXISTS (SELECT 1 FROM mining.work_topic wt JOIN mining.topics t USING (topic_id) "
            "WHERE wt.work_id = w.work_id AND (t.slug = %s OR t.parent_id = "
            "(SELECT topic_id FROM mining.topics WHERE slug = %s)))"
        )
        params += [topic, topic]
    if year_from:
        where.append("w.publication_year >= %s")
        params.append(year_from)
    where_sql = " AND ".join(where) if where else "TRUE"
    order = "w.cited_by_count DESC" if sort == "citations" else "w.publication_year DESC, w.cited_by_count DESC"

    rows = db.query(
        f"""
        SELECT w.work_id, w.title, w.abstract, w.publication_year, w.publication_date,
               w.cited_by_count, w.doi, w.source_name,
               COALESCE((
                   SELECT json_agg(json_build_object('slug', t.slug, 'name_zh', t.name_zh))
                   FROM (SELECT topic_id FROM mining.work_topic WHERE work_id = w.work_id
                         LIMIT 2) wt2
                   JOIN mining.topics t USING (topic_id)
               ), '[]'::json) AS topics,
               COALESCE((
                   SELECT json_agg(json_build_object(
                              'person_id', pp.person_id, 'name', pp.display_name,
                              'selected', pp.is_selected) ORDER BY pw.author_position)
                   FROM (SELECT person_id, author_position FROM mining.person_work
                         WHERE work_id = w.work_id LIMIT 8) pw
                   JOIN mining.persons pp ON pp.person_id = pw.person_id
               ), '[]'::json) AS authors
        FROM mining.works w
        WHERE {where_sql}
        ORDER BY {order}
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    total = db.query_one(
        f"SELECT COUNT(*) AS n FROM mining.works w WHERE {where_sql}", tuple(params)
    )["n"]
    return {"total": total, "works": rows}
