"""处理管线：pending 条目 → 过滤/分类/摘要/评分 → approved/rejected。"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from .. import config, db
from . import heuristic, llm

log = logging.getLogger(__name__)

MAX_PROCESS_ITEMS_UNBOUNDED = 5000


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


def normalize_title(t: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]", "", (t or "").lower())


def _save_item(
    item: dict,
    result: dict,
    status: str,
    relevance: float,
    authority: float,
    freshness: float,
    depth: float,
    final_score: float,
    title_norm: str,
    topic_map: dict[str, int],
) -> str:
    """原子写入条目判定结果与主题关联；返回最终状态（可能因去重改为 rejected）。"""
    with db.transaction():
        if status == "approved":
            dup = db.query_one(
                """
                SELECT item_id FROM mining.items
                WHERE item_id <> %s
                  AND status IN ('approved', 'pending')
                  AND (title_norm = %s
                       OR similarity(title_norm, %s) >= 0.6)
                LIMIT 1
                """,
                (item["item_id"], title_norm, title_norm),
            )
            if dup:
                status = "rejected"
                result["reject_reason"] = "重复新闻（其他信源已收录同一事件）"

        db.execute(
            """
            UPDATE mining.items
            SET summary_zh = %s, item_type = %s,
                mining_relevance = %s, authority = %s, freshness = %s, depth = %s,
                final_score = %s, status = %s, status_source = %s,
                reject_reason = %s, title_norm = %s, processed_at = now()
            WHERE item_id = %s
            """,
            (
                result.get("summary_zh"), result.get("item_type") or "news",
                relevance, authority, freshness, depth, final_score, status,
                result.get("status_source", "heuristic"), result.get("reject_reason"),
                title_norm, item["item_id"],
            ),
        )

        if status == "approved":
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
    return status


def process_item(item: dict, source: dict, topic_map: dict[str, int]) -> dict:
    title_norm = normalize_title(item["title"])
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
            log.exception("LLM classify failed, falling back to heuristic: %s", title[:80])
            result = heuristic.classify(title, summary_raw, site_url, source_type)
    else:
        result = heuristic.classify(title, summary_raw, site_url, source_type)
    result["status_source"] = status_source

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
    # LLM/heuristic 的 relevant 判定即最终结论（其内部已含阈值）；
    # 避免"relevant=true 但分数略低"时被静默拒绝且无原因
    status = "approved" if result.get("relevant") else "rejected"

    status = _save_item(
        item, result, status, relevance, authority, freshness, depth,
        final_score, title_norm, topic_map,
    )
    return {"item_id": item["item_id"], "status": status, "score": final_score}


def _fetch_pending(batch_size: int) -> list[dict]:
    return db.query(
        """
        SELECT i.item_id, i.title, i.summary_raw, i.published_at, i.collected_at,
               s.site_url, s.source_type, s.authority_weight
        FROM mining.items i
        JOIN mining.sources s USING (source_id)
        WHERE i.status = 'pending'
        ORDER BY i.item_id
        LIMIT %s
        """,
        (batch_size,),
    )


def run_process(limit: int | None = None) -> dict:
    """处理 pending 条目。

    limit 指定时只处理一批（便于 CLI 调试）；未指定时循环处理直到清空，
    单次最多 MAX_PROCESS_ITEMS_UNBOUNDED 条，避免异常数据导致无限循环。
    """
    batch_size = limit or config.PROCESS_BATCH_SIZE
    max_items = limit if limit is not None else MAX_PROCESS_ITEMS_UNBOUNDED

    topic_rows = db.query("SELECT topic_id, slug FROM mining.topics")
    topic_map = {r["slug"]: r["topic_id"] for r in topic_rows}

    processed = approved = rejected = errors = 0
    while processed < max_items:
        take = min(batch_size, max_items - processed)
        items = _fetch_pending(take)
        if not items:
            break
        for item in items:
            source = {
                "site_url": item["site_url"], "source_type": item["source_type"],
                "authority_weight": item["authority_weight"],
            }
            try:
                outcome = process_item(item, source, topic_map)
                if outcome["status"] == "approved":
                    approved += 1
                else:
                    rejected += 1
            except Exception as exc:
                errors += 1
                log.exception("process item %s failed", item["item_id"])
                # 避免坏条目永久停留在 pending 并阻塞后续批次
                try:
                    db.execute(
                        "UPDATE mining.items SET status = 'rejected', "
                        "reject_reason = %s, processed_at = now() WHERE item_id = %s",
                        (f"处理失败：{exc}"[:300], item["item_id"]),
                    )
                except Exception:
                    log.exception("failed to mark item %s rejected", item["item_id"])
        processed += len(items)
        if len(items) < take:
            break

    result = {
        "processed": processed, "approved": approved,
        "rejected": rejected, "errors": errors,
    }
    print(f"processed: {processed} (approved {approved}, rejected {rejected}, errors {errors})")
    log.info("process finished: %s", result)
    return result
