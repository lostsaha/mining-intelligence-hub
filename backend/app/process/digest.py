"""周报生成：按 ISO 周（周一起）聚合 approved 条目，主题多样性优先。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .. import db

GLOBAL_TOP = 20
PER_TOPIC_TOP = 5


def week_start_of(day: date | None = None) -> date:
    day = day or datetime.now(timezone.utc).date()
    return day - timedelta(days=day.weekday())  # 周一


def _candidate_items(week_start: date) -> list[dict]:
    start = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return db.query(
        """
        SELECT i.item_id, i.title, i.url, i.summary_zh, i.final_score, i.item_type,
               i.published_at, s.name AS source_name, s.slug AS source_slug,
               COALESCE(
                   (SELECT t.slug FROM mining.item_topic it
                    JOIN mining.topics t USING (topic_id)
                    WHERE it.item_id = i.item_id
                    ORDER BY it.relevance DESC LIMIT 1), 'industry'
               ) AS primary_topic
        FROM mining.items i
        JOIN mining.sources s USING (source_id)
        WHERE i.status = 'approved'
          AND COALESCE(i.published_at, i.collected_at) >= %s
          AND COALESCE(i.published_at, i.collected_at) < %s
        ORDER BY i.final_score DESC
        LIMIT 300
        """,
        (start, end),
    )


def select_items(items: list[dict]) -> list[dict]:
    """先保证每主题入选（每主题最多 5 条），再按全局分补足。"""
    chosen: list[int] = []
    result: list[dict] = []

    def take(item: dict) -> None:
        if item["item_id"] not in chosen:
            chosen.append(item["item_id"])
            result.append(item)

    per_topic_counts: dict[str, int] = {}
    for item in items:  # 已按 final_score 降序
        t = item["primary_topic"]
        if per_topic_counts.get(t, 0) < PER_TOPIC_TOP:
            take(item)
            per_topic_counts[t] = per_topic_counts.get(t, 0) + 1
        if len(result) >= GLOBAL_TOP:
            return result
    for item in items:
        if len(result) >= GLOBAL_TOP:
            break
        take(item)
    return result


def generate(week_start: date | None = None) -> dict:
    week_start = week_start or week_start_of()
    items = _candidate_items(week_start)
    if not items:
        return {"digest_id": None, "week_start": str(week_start), "item_count": 0,
                "message": "该周没有已审核条目，请先运行采集与处理管线"}

    selected = select_items(items)
    title = f"矿业前沿周报 · {week_start.isoformat()}"
    n_topics = len({i["primary_topic"] for i in selected})
    summary = f"本周精选 {len(selected)} 条动态，覆盖 {n_topics} 个主题方向。"

    digest = db.query_one(
        """
        INSERT INTO mining.weekly_digests (week_start, title, summary, item_count)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (week_start) DO UPDATE
        SET title = EXCLUDED.title, summary = EXCLUDED.summary,
            item_count = EXCLUDED.item_count, generated_at = now()
        RETURNING digest_id
        """,
        (week_start, title, summary, len(selected)),
    )
    db.execute("DELETE FROM mining.digest_item WHERE digest_id = %s", (digest["digest_id"],))
    for rank, item in enumerate(selected, start=1):
        db.execute(
            """
            INSERT INTO mining.digest_item (digest_id, item_id, topic_id, rank)
            VALUES (%s, %s,
                    (SELECT topic_id FROM mining.topics WHERE slug = %s), %s)
            ON CONFLICT DO NOTHING
            """,
            (digest["digest_id"], item["item_id"], item["primary_topic"], rank),
        )

    print(f"digest {week_start}: {len(selected)} items / {n_topics} topics")
    return {"digest_id": digest["digest_id"], "week_start": str(week_start),
            "item_count": len(selected)}
