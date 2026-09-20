"""把 data/topics.yaml 与 data/sources.yaml 同步进数据库（幂等 upsert）。"""
import sys
from pathlib import Path

import yaml

from . import config, db


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def seed_topics() -> int:
    data = _load_yaml(config.DATA_DIR / "topics.yaml")
    count = 0
    for t in data["topics"]:
        row = db.query_one(
            """
            INSERT INTO mining.topics (slug, name_zh, name_en, level, sort_order)
            VALUES (%s, %s, %s, 1, %s)
            ON CONFLICT (slug) DO UPDATE
            SET name_zh = EXCLUDED.name_zh,
                name_en = EXCLUDED.name_en,
                sort_order = EXCLUDED.sort_order
            RETURNING topic_id
            """,
            (t["slug"], t["name_zh"], t["name_en"], t.get("sort_order", 0)),
        )
        count += 1
        parent_id = row["topic_id"]
        for idx, child in enumerate(t.get("children", []) or []):
            db.execute(
                """
                INSERT INTO mining.topics (slug, name_zh, name_en, parent_id, level, sort_order)
                VALUES (%s, %s, %s, %s, 2, %s)
                ON CONFLICT (slug) DO UPDATE
                SET name_zh = EXCLUDED.name_zh,
                    name_en = EXCLUDED.name_en,
                    parent_id = EXCLUDED.parent_id,
                    sort_order = EXCLUDED.sort_order
                """,
                (
                    child["slug"], child["name_zh"], child["name_en"],
                    parent_id, t.get("sort_order", 0) * 100 + idx + 1,
                ),
            )
            count += 1
    return count


def seed_sources() -> int:
    data = _load_yaml(config.DATA_DIR / "sources.yaml")
    count = 0
    for s in data["sources"]:
        db.execute(
            """
            INSERT INTO mining.sources
                (slug, name, layer, source_type, feed_url, site_url, lang,
                 authority_weight, active, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                layer = EXCLUDED.layer,
                source_type = EXCLUDED.source_type,
                feed_url = EXCLUDED.feed_url,
                site_url = EXCLUDED.site_url,
                lang = EXCLUDED.lang,
                authority_weight = EXCLUDED.authority_weight,
                active = EXCLUDED.active,
                notes = EXCLUDED.notes
            """,
            (
                s["slug"], s["name"], s.get("layer", 4), s.get("source_type", "news"),
                s.get("feed_url"), s.get("site_url"), s.get("lang", "en"),
                s.get("authority_weight", 5), s.get("active", True), s.get("notes"),
            ),
        )
        count += 1
    return count


def main() -> None:
    n_topics = seed_topics()
    n_sources = seed_sources()
    print(f"seeded: {n_topics} topics, {n_sources} sources")


if __name__ == "__main__":
    sys.exit(main())
