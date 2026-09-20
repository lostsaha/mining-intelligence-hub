"""FastAPI 后端：为前端提供数据接口 + 触发采集/处理/周报的管理端点。"""
from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException, Query

from . import db
from .api import graph as graph_api
from .api import radar as radar_api
from .api import works_api
from .collect.run import run_collect
from .process import digest as digest_mod
from .process import pipeline

app = FastAPI(title="矿业前沿情报聚合平台 API", version="0.1.0")

# 简单互斥：避免采集任务并发重入
_job_lock = threading.Lock()
_job_state = {"running": False, "last_result": None}

TOPIC_STATS_SQL = """
SELECT t.slug, t.name_zh, t.name_en, t.sort_order,
       COUNT(it.item_id) FILTER (
           WHERE COALESCE(i.published_at, i.collected_at) >= now() - interval '30 days'
       ) AS item_count,
       COUNT(it.item_id) AS item_count_all
FROM mining.topics t
LEFT JOIN mining.item_topic it ON it.topic_id = t.topic_id
LEFT JOIN mining.items i ON i.item_id = it.item_id AND i.status = 'approved'
GROUP BY t.topic_id, t.slug, t.name_zh, t.name_en, t.sort_order
ORDER BY t.sort_order
"""

ITEM_FIELDS = """
i.item_id, i.title, i.url, i.summary_zh, i.summary_raw, i.item_type,
i.published_at, i.collected_at, i.final_score, i.mining_relevance, i.status,
s.name AS source_name, s.slug AS source_slug, s.lang AS source_lang
"""


def _items_with_topics(where: str, params: tuple) -> list[dict]:
    rows = db.query(
        f"""
        SELECT {ITEM_FIELDS},
               COALESCE(
                   (SELECT json_agg(json_build_object('slug', t.slug, 'name_zh', t.name_zh)
                                    ORDER BY t.sort_order)
                    FROM mining.item_topic it JOIN mining.topics t USING (topic_id)
                    WHERE it.item_id = i.item_id),
                   '[]'::json
               ) AS topics
        FROM mining.items i
        JOIN mining.sources s USING (source_id)
        {where}
        ORDER BY COALESCE(i.published_at, i.collected_at) DESC
        """,
        params,
    )
    return rows


# ---------------------------------------------------------------- 条目
@app.get("/api/items")
def list_items(
    topic: str | None = None,
    days: int = 30,
    limit: int = Query(50, le=200),
    offset: int = 0,
    q: str | None = None,
):
    where = ["i.status = 'approved'",
             "COALESCE(i.published_at, i.collected_at) >= now() - (%s || ' days')::interval"]
    params: list = [days]
    if topic:
        where.append(
            "EXISTS (SELECT 1 FROM mining.item_topic it JOIN mining.topics t USING (topic_id) "
            "WHERE it.item_id = i.item_id AND t.slug = %s)"
        )
        params.append(topic)
    if q:
        where.append("(i.title ILIKE %s OR i.summary_zh ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    where_sql = " AND ".join(where)
    rows = _items_with_topics(f"WHERE {where_sql}", tuple(params))
    total = db.query_one(
        f"""
        SELECT COUNT(*) AS n
        FROM mining.items i
        WHERE {where_sql}
        """,
        tuple(params),
    )["n"]
    return {"total": total, "items": rows[offset: offset + limit]}


# ---------------------------------------------------------------- 主题
@app.get("/api/topics")
def list_topics():
    return {"topics": db.query(TOPIC_STATS_SQL)}


@app.get("/api/topics/{slug}")
def topic_detail(slug: str, limit: int = Query(100, le=300)):
    topic = db.query_one(
        "SELECT slug, name_zh, name_en FROM mining.topics WHERE slug = %s", (slug,)
    )
    if not topic:
        raise HTTPException(404, "topic not found")
    rows = db.query(
        f"""
        SELECT {ITEM_FIELDS}
        FROM mining.items i
        JOIN mining.sources s USING (source_id)
        JOIN mining.item_topic it ON it.item_id = i.item_id
        JOIN mining.topics t ON t.topic_id = it.topic_id
        WHERE i.status = 'approved' AND t.slug = %s
        ORDER BY i.final_score DESC, COALESCE(i.published_at, i.collected_at) DESC
        LIMIT %s
        """,
        (slug, limit),
    )
    return {**topic, "items": rows}


# ---------------------------------------------------------------- 周报
@app.get("/api/weekly")
def list_weekly():
    return {"digests": db.query(
        "SELECT digest_id, week_start, title, summary, item_count, generated_at "
        "FROM mining.weekly_digests ORDER BY week_start DESC"
    )}


@app.get("/api/weekly/{digest_id}")
def weekly_detail(digest_id: int):
    digest = db.query_one(
        "SELECT digest_id, week_start, title, summary, item_count, generated_at "
        "FROM mining.weekly_digests WHERE digest_id = %s",
        (digest_id,),
    )
    if not digest:
        raise HTTPException(404, "digest not found")
    rows = db.query(
        f"""
        SELECT di.rank, di.topic_id, t.slug AS topic_slug, t.name_zh AS topic_name_zh,
               t.sort_order AS topic_order, {ITEM_FIELDS}
        FROM mining.digest_item di
        JOIN mining.items i ON i.item_id = di.item_id
        JOIN mining.sources s USING (source_id)
        LEFT JOIN mining.topics t ON t.topic_id = di.topic_id
        WHERE di.digest_id = %s
        ORDER BY di.rank
        """,
        (digest_id,),
    )
    # 按主题分组（保持 rank 顺序）
    groups: dict[str, dict] = {}
    for r in rows:
        key = r["topic_slug"] or "industry"
        groups.setdefault(key, {
            "slug": key,
            "name_zh": r["topic_name_zh"] or "行业与市场",
            "items": [],
        })
        groups[key]["items"].append(r)
    return {**digest, "groups": list(groups.values())}


# ---------------------------------------------------------------- 信源
@app.get("/api/sources")
def list_sources():
    rows = db.query(
        """
        SELECT s.source_id, s.slug, s.name, s.layer, s.source_type, s.site_url,
               s.lang, s.authority_weight, s.active, s.notes, s.last_fetched_at,
               COUNT(i.item_id) FILTER (WHERE i.status = 'approved') AS approved_count
        FROM mining.sources s
        LEFT JOIN mining.items i ON i.source_id = s.source_id
        GROUP BY s.source_id
        ORDER BY s.layer, s.authority_weight DESC, s.name
        """
    )
    layers = {
        1: "专家个人", 2: "矿业公司", 3: "专业组织", 4: "期刊 / 会议 / 行业媒体",
    }
    grouped: dict[int, list] = {}
    for r in rows:
        grouped.setdefault(r["layer"], []).append(r)
    return {"layers": [{"layer": k, "name": layers[k], "sources": grouped.get(k, [])}
                       for k in sorted(grouped)]}


# ---------------------------------------------------------------- 专家（Phase 2）


@app.get("/api/experts")
def list_experts(
    topic: str | None = None,
    q: str | None = None,
    tier: str | None = None,
    limit: int = Query(100, le=200),
):
    where = []  # 名册人员（is_selected=false）也要能出现在认证筛选里
    params: list = []
    if tier == "certified":
        where.append("ea.tier IS NOT NULL")
    elif tier:
        where.append("ea.tier = %s")
        params.append(tier)
    else:
        where.append("p.is_selected")
    if topic:
        where.append(
            "EXISTS (SELECT 1 FROM mining.person_topic pt JOIN mining.topics t USING (topic_id) "
            "WHERE pt.person_id = p.person_id AND (t.slug = %s OR t.parent_id = "
            "(SELECT topic_id FROM mining.topics WHERE slug = %s)))"
        )
        params += [topic, topic]
    if q:
        where.append("(p.display_name ILIKE %s OR i.name ILIKE %s OR ea.name_zh ILIKE %s)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    rows = db.query(
        f"""
        SELECT p.person_id, p.display_name, p.expert_rank, p.final_score, p.expert_score,
               p.corpus_works, p.corpus_citations, p.last_year,
               p.country_code, p.orcid, p.summary_zh,
               (p.raw_data->>'h_index') AS h_index,
               i.name AS institution_name,
               ea.tier AS admission_tier, ea.channel AS admission_channel,
               ea.name_zh AS admission_name_zh,
               COALESCE((
                   SELECT json_agg(json_build_object('slug', t.slug, 'name_zh', t.name_zh)
                                   ORDER BY pt.works_count DESC)
                   FROM (SELECT topic_id, works_count FROM mining.person_topic
                         WHERE person_id = p.person_id
                         ORDER BY works_count DESC LIMIT 3) pt
                   JOIN mining.topics t USING (topic_id)
               ), '[]'::json) AS topics
        FROM mining.persons p
        LEFT JOIN mining.institutions i ON i.institution_id = p.current_institution_id
        LEFT JOIN mining.expert_admissions ea ON ea.person_id = p.person_id
        WHERE {" AND ".join(where)}
        ORDER BY (ea.tier IS NOT NULL) DESC NULLS LAST,
                 p.final_score DESC NULLS LAST
        LIMIT %s
        """,
        (*params, limit),
    )
    return {"total": len(rows), "experts": rows}


@app.get("/api/experts/meta")
def experts_meta():
    rows = db.query(
        """
        SELECT t.slug, t.name_zh, t.name_en, t.sort_order, COUNT(DISTINCT pt.person_id) AS expert_count
        FROM mining.topics t
        LEFT JOIN mining.topics ch ON ch.parent_id = t.topic_id
        LEFT JOIN mining.person_topic pt ON pt.topic_id = t.topic_id OR pt.topic_id = ch.topic_id
        JOIN mining.persons p ON p.person_id = pt.person_id AND p.is_selected
        WHERE t.level = 1
        GROUP BY t.topic_id, t.slug, t.name_zh, t.name_en, t.sort_order
        ORDER BY t.sort_order
        """
    )
    total = db.query_one("SELECT COUNT(*) AS n FROM mining.persons WHERE is_selected")["n"]
    return {"total": total, "categories": [r for r in rows if r["expert_count"] > 0]}


@app.get("/api/admissions")
def admissions_compare():
    """名册 × 算法榜对照：高置信 / 算法盲区 / 独立记录。"""
    rows = db.query(
        """
        SELECT ea.admission_id, ea.roster_key, ea.full_name, ea.name_zh, ea.tier,
               ea.channel, ea.affiliation, ea.country_code, ea.basis,
               ea.match_status, ea.match_confidence::float AS confidence,
               p.person_id, p.is_selected, p.final_score, p.expert_rank,
               p.corpus_works, p.display_name AS algo_name,
               i.name AS institution_name
        FROM mining.expert_admissions ea
        LEFT JOIN mining.persons p ON p.person_id = ea.person_id
        LEFT JOIN mining.institutions i ON i.institution_id = p.current_institution_id
        ORDER BY ea.tier, p.final_score DESC NULLS LAST
        """
    )
    by_tier: dict[str, int] = {}
    for r in rows:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    dual = [r for r in rows if r["is_selected"]]
    blind_spot = [r for r in rows if r["tier"] and not r["is_selected"]]
    independent = [r for r in rows if r["match_status"] == "created"]
    algo_only = db.query_one(
        "SELECT COUNT(*) AS n FROM mining.persons p "
        "WHERE p.is_selected AND NOT EXISTS ("
        "  SELECT 1 FROM mining.expert_admissions ea WHERE ea.person_id = p.person_id)"
    )["n"]
    return {
        "total": len(rows),
        "by_tier": by_tier,
        "dual_count": len(dual),
        "blind_spot_count": len(blind_spot),
        "independent_count": len(independent),
        "algo_only_count": algo_only,
        "rows": rows,
        "dual": dual,
        "blind_spot": blind_spot,
        "independent": independent,
    }


@app.get("/api/experts/{person_id}")
def expert_detail(person_id: int):
    person = db.query_one(
        """
        SELECT p.*, i.name AS institution_name, i.country_code AS inst_country,
               i.institution_type AS inst_type,
               ea.tier AS admission_tier, ea.channel AS admission_channel,
               ea.basis AS admission_basis, ea.name_zh AS admission_name_zh,
               ea.match_status AS admission_match_status
        FROM mining.persons p
        LEFT JOIN mining.institutions i ON i.institution_id = p.current_institution_id
        LEFT JOIN mining.expert_admissions ea ON ea.person_id = p.person_id
        WHERE p.person_id = %s
        """,
        (person_id,),
    )
    if not person:
        raise HTTPException(404, "expert not found")

    topics = db.query(
        """
        SELECT t.topic_id, t.slug, t.name_zh, t.name_en, t.level,
               ptp.relevance, ptp.works_count, ptp.citation_count,
               ptp.first_year, ptp.last_year,
               pt2.name_zh AS parent_name, pt2.slug AS parent_slug,
               pt2.sort_order AS parent_order
        FROM mining.person_topic ptp
        JOIN mining.topics t ON t.topic_id = ptp.topic_id
        LEFT JOIN mining.topics pt2 ON pt2.topic_id = t.parent_id
        WHERE ptp.person_id = %s
        ORDER BY ptp.works_count DESC
        """,
        (person_id,),
    )
    evidence = db.query(
        "SELECT evidence_type, claim FROM mining.evidence "
        "WHERE entity_type = 'person' AND entity_id = %s",
        (person_id,),
    )
    recent_works = db.query(
        """
        SELECT w.work_id, w.title, w.publication_year, w.cited_by_count,
               w.doi, w.source_name
        FROM mining.person_work pw
        JOIN mining.works w USING (work_id)
        WHERE pw.person_id = %s
          AND w.publication_year >= (SELECT MAX(publication_year) FROM mining.works) - 4
        ORDER BY w.cited_by_count DESC
        LIMIT 8
        """,
        (person_id,),
    )
    coauthors = db.query(
        """
        SELECT p2.person_id, p2.display_name, p2.is_selected, COUNT(*) AS shared_works
        FROM mining.person_work pw1
        JOIN mining.person_work pw2
          ON pw1.work_id = pw2.work_id AND pw1.person_id <> pw2.person_id
        JOIN mining.persons p2 ON p2.person_id = pw2.person_id
        WHERE pw1.person_id = %s
        GROUP BY p2.person_id, p2.display_name, p2.is_selected
        ORDER BY shared_works DESC
        LIMIT 6
        """,
        (person_id,),
    )
    history = db.query(
        "SELECT score_date, final_score, expert_score, rank "
        "FROM mining.expert_score_history WHERE person_id = %s ORDER BY score_date",
        (person_id,),
    )
    return {"person": person, "topics": topics, "evidence": evidence,
            "recent_works": recent_works, "coauthors": coauthors, "history": history}


# ---------------------------------------------------------------- 雷达 / 图谱 / 文献（Phase 3）
@app.get("/api/radar")
def api_radar(level: int = Query(2, ge=1, le=2), parent: str | None = None):
    """前沿技术雷达：level=2 子主题（默认）或 level=1 大类。"""
    return radar_api.radar(level=level, parent_slug=parent)


@app.get("/api/graph")
def api_graph(topic: str = "geotech-slope", expert_limit: int = Query(24, le=50)):
    """以主题为中心的知识图谱子图。"""
    return graph_api.subgraph(topic, expert_limit=expert_limit)


@app.get("/api/works")
def api_works(
    q: str | None = None,
    topic: str | None = None,
    year_from: int | None = None,
    sort: str = "citations",
    limit: int = Query(30, le=100),
    offset: int = 0,
):
    """文献检索（标题/摘要）。sort=citations|year"""
    return works_api.search_works(
        q=q, topic=topic, year_from=year_from, sort=sort, limit=limit, offset=offset
    )


# ---------------------------------------------------------------- 统计 / 管理
@app.get("/api/stats")
def stats():
    items = db.query_one(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'approved') AS approved,
               COUNT(*) FILTER (WHERE status = 'pending') AS pending,
               COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
               MAX(collected_at) AS last_collected
        FROM mining.items
        """
    )
    sources = db.query_one(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE active) AS active FROM mining.sources"
    )
    digests = db.query_one("SELECT COUNT(*) AS total FROM mining.weekly_digests")
    last_run = db.query_one(
        "SELECT run_id, started_at, finished_at, sources_ok, sources_failed, items_new "
        "FROM mining.collect_runs ORDER BY run_id DESC LIMIT 1"
    )
    return {"items": items, "sources": sources, "digests": digests, "last_run": last_run,
            "job_running": _job_state["running"]}


@app.post("/api/admin/run-pipeline")
def run_pipeline():
    """后台执行一轮完整管线：采集 → 处理 → 周报。立即返回，用 /api/stats 轮询。"""
    if _job_state["running"]:
        return {"started": False, "message": "已有任务在运行中"}

    def _job():
        _job_state["running"] = True
        result = {}
        try:
            result["collect"] = run_collect()
            result["process"] = pipeline.run_process()
            result["digest"] = digest_mod.generate()
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            _job_state["running"] = False
            _job_state["last_result"] = result

    threading.Thread(target=_job, daemon=True).start()
    return {"started": True, "message": "管线已启动：采集 → 过滤评分 → 周报生成"}
