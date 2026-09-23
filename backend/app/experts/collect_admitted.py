"""名册专家定向采集：按已匹配的 OpenAlex 作者 ID 拉取全部作品（近年为子集）。

与关键词采集互补：关键词负责"发现"语料，作者 ID 负责"保底"名册专家的完整成果——
这是消除院士盲区的主要手段（中文文献经 OpenAlex 中文检索进入作者作品列表）。
用法：python -m app.experts.collect_admitted [--tier T2]
"""
from __future__ import annotations

import json
import time

import yaml

from .. import config, db
from ..openalex.client import BudgetExhausted, OpenAlexClient, reconstruct_abstract
from .collect_works import (
    build_authorships_cache,
    flush_authorships,
    load_ontology,
    upsert_work,
)

SELECT = ("id,doi,title,publication_year,publication_date,cited_by_count,type,language,"
          "authorships,primary_location,abstract_inverted_index")


def _flat_classifier(ontology: list[dict]) -> list[dict]:
    """展平全部子主题+大类，用于无类目上下文的作者作品分类。"""
    flat = []
    for cat in ontology:
        for ch in cat["children"]:
            flat.append({
                "topic_id": ch["topic_id"],
                "en": [k.lower() for k in ch["match_keywords"]],
                "zh": [k for k in ch.get("match_keywords_zh", [])] + [ch["name_zh"]],
            })
        flat.append({
            "topic_id": cat["topic_id"],
            "en": [k.lower() for k in cat["match_keywords"]],
            "zh": [k for k in cat.get("match_keywords_zh", [])] + [cat["name_zh"]],
        })
    return flat


def global_classify(text: str, flat: list[dict]) -> list[tuple[int, float]]:
    scored = []
    for t in flat:
        hits = sum(1 for k in t["en"] if k in text)
        hits += sum(1 for k in t.get("zh", []) if k and k in text)
        if hits:
            scored.append((t["topic_id"], min(0.9, 0.5 + 0.1 * hits)))
    scored.sort(key=lambda x: -x[1])
    return scored[:2]


def collect_admitted(tiers: tuple[str, ...] = ("T1",), per_author_cap: int = 400) -> dict:
    ontology = load_ontology()
    flat = _flat_classifier(ontology)
    client = OpenAlexClient()

    run = db.query_one(
        "INSERT INTO mining.expert_pipeline_runs (run_type) VALUES ('admitted') RETURNING run_id"
    )

    authors = db.query(
        """
        SELECT p.person_id, p.openalex_id, p.display_name,
               COALESCE(ea.name_zh, ea.full_name) AS roster_name, ea.tier
        FROM mining.expert_admissions ea
        JOIN mining.persons p ON p.person_id = ea.person_id
        WHERE ea.match_status = 'matched' AND p.openalex_id IS NOT NULL
          AND ea.tier = ANY(%s)
        ORDER BY ea.tier, ea.admission_id
        """,
        (list(tiers),),
    )
    print(f"admitted collect: {len(authors)} authors (tiers={tiers})")

    caches = {
        "persons": {}, "persons_display": {}, "institutions": set(),
        "inst_rows": [], "pw": [], "pi": [],
    }
    total = recent_total = 0
    detail = []
    current_year = time.gmtime().tm_year

    for i, a in enumerate(authors, start=1):
        author_id = a["openalex_id"].rsplit("/", 1)[-1]
        n_works = n_recent = 0
        try:
            cursor = "*"
            while cursor:
                data = client.get(
                    "/works",
                    {"filter": f"author.id:{author_id},from_publication_date:1990-01-01",
                     "sort": "publication_date:desc", "per-page": 200,
                     "cursor": cursor, "select": SELECT},
                )
                for work in data.get("results", []):
                    work_db_id = upsert_work(work)
                    if work_db_id is None:
                        continue
                    text = f"{work.get('title') or ''} {reconstruct_abstract(work.get('abstract_inverted_index'))}".lower()
                    for topic_id, rel in global_classify(text, flat):
                        db.execute(
                            "INSERT INTO mining.work_topic (work_id, topic_id, relevance) "
                            "VALUES (%s, %s, %s) ON CONFLICT (work_id, topic_id) DO NOTHING",
                            (work_db_id, topic_id, rel),
                        )
                    build_authorships_cache(work.get("authorships", []) or [], work_db_id, caches)
                    n_works += 1
                    if (work.get("publication_year") or 0) >= current_year - 5:
                        n_recent += 1
                    if n_works >= per_author_cap:
                        break
                cursor = (data.get("meta") or {}).get("next_cursor")
                if n_works >= per_author_cap:
                    break
                time.sleep(0.12)
        except BudgetExhausted as exc:
            print(f"[budget] 停止 @ {a['roster_name']}: {str(exc)[:80]}")
            detail.append({"author": a["roster_name"], "stopped": True})
            break
        except Exception as exc:
            print(f"[fail] {a['roster_name']}: {str(exc)[:100]}")
            detail.append({"author": a["roster_name"], "error": str(exc)[:150]})
            continue
        flush_authorships(caches)
        total += n_works
        recent_total += n_recent
        detail.append({"author": a["roster_name"], "openalex_id": author_id,
                       "works": n_works, "recent": n_recent})
        print(f"[{i}/{len(authors)}] {a['roster_name']}: +{n_works} 作品（近年 {n_recent}）")

    flush_authorships(caches)
    db.execute(
        """
        UPDATE mining.expert_pipeline_runs
        SET finished_at = now(), works_collected = %s, detail = %s
        WHERE run_id = %s
        """,
        (total, json.dumps({"authors": len(authors), "recent_total": recent_total,
                            "detail": detail}, ensure_ascii=False), run["run_id"]),
    )
    client.close()
    return {"authors": len(authors), "works_collected": total, "recent_subset": recent_total}


if __name__ == "__main__":
    import sys
    tiers = ("T1", "T2") if "--tier" not in sys.argv else (sys.argv[sys.argv.index("--tier") + 1],)
    print(collect_admitted(tiers=tiers))
