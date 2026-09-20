"""处理管线：pending 条目 → 过滤/分类/摘要/评分 → approved/rejected。"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import config, db
from . import heuristic, llm


def _freshness(published_at: datetime | None, collected_at: datetime) -> float:
    ref = published_at or collected_at
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (datetime.now(timezone.utc) - ref).total_seconds() / 86400)
    return round(0.5 ** (age_days / config.FRESHNESS_HALF_LIFE_DAYS), 3)


def _depth(title: str, summary_raw: str | None, item_type: str) -> float:
    length = len(title or "") + len(summary_raw or "")
    score = min(1.0, length / 600)
    if item_type in ("paper", "report"):
        score = min(1.0, score + 0.2)
    return round(score, 3)


def process_item(item: dict, source: dict, topic_map: dict[str, int]) -> dict:
    site_url = source.get("site_url") or ""
    source_type = source.get("source_type") or "news"
    title = item["title"] or ""
    summary_raw = item.get("summary_raw") or ""

    status_source = "heuristic"
    if config.LLM_ENABLED:
        try:
            result = llm.classify(title, summary_raw, site_url, source_type)
            status_source = "llm"
        except Exception:
            result = heuristic.classify(title, summary_raw, site_url, source_type)
    else:
        result = heuristic.classify(title, summary_raw, site_url, source_type)

    item_type = result.get("item_type") or "news"
    relevance = float(result.get("relevance", 0))
    authority = float(source["authority_weight"]) / 10.0
    freshness = _freshness(item.get("published_at"), item["collected_at"])
    depth = _depth(title, summary_raw, item_type)

    w = config.WEIGHTS
    final_score = round(
        100 * (w["relevance"] * relevance + w["authority"] * authority
               + w["freshness"] * freshness + w["depth"] * depth), 2
    )
    status = "approved" if result.get("relevant") and relevance >= config.RELEVANCE_APPROVE_THRESHOLD else "rejected"

    db.execute(
        """
        UPDATE mining.items
        SET summary_zh = %s, item_type = %s,
            mining_relevance = %s, authority = %s, freshness = %s, depth = %s,
            final_score = %s, status = %s, status_source = %s,
            reject_reason = %s, processed_at = now()
        WHERE item_id = %s
        """,
        (
            result.get("summary_zh"), item_type, relevance, authority, freshness,
            depth, final_score, status, status_source, result.get("reject_reason"),
            item["item_id"],
        ),
    )

    for slug in result.get("topics", []):
        topic_id = topic_map.get(slug)
        if topic_id:
            db.execute(
                """
                INSERT INTO mining.item_topic (item_id, topic_id, relevance)
                VALUES (%s, %s, %s)
                ON CONFLICT (item_id, topic_id) DO NOTHING
                """,
                (item["item_id"], topic_id, relevance),
            )

    return {"item_id": item["item_id"], "status": status, "score": final_score}


def run_process(limit: int | None = None) -> dict:
    limit = limit or config.PROCESS_BATCH_SIZE
    items = db.query(
        """
        SELECT i.item_id, i.title, i.summary_raw, i.published_at, i.collected_at,
               s.site_url, s.source_type, s.authority_weight
        FROM mining.items i
        JOIN mining.sources s USING (source_id)
        WHERE i.status = 'pending'
        ORDER BY i.item_id
        LIMIT %s
        """,
        (limit,),
    )
    topic_rows = db.query("SELECT topic_id, slug FROM mining.topics")
    topic_map = {r["slug"]: r["topic_id"] for r in topic_rows}

    approved = rejected = 0
    for item in items:
        source = {
            "site_url": item["site_url"], "source_type": item["source_type"],
            "authority_weight": item["authority_weight"],
        }
        outcome = process_item(item, source, topic_map)
        if outcome["status"] == "approved":
            approved += 1
        else:
            rejected += 1

    print(f"processed: {len(items)} (approved {approved}, rejected {rejected})")
    return {"processed": len(items), "approved": approved, "rejected": rejected}
