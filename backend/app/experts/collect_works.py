"""作品采集管线：本体查询词族 → OpenAlex works → 归类子主题 → 连同作者/机构入库。

对应 PDF 记录 §17 管线的 01~03 步（load_mining_topics → query_openalex_works →
extract_authors），入库即建立 Person—Work—Topic—Institution 闭环。
"""
from __future__ import annotations

import json
import re
import time

import yaml

from .. import config, db
from ..openalex.client import BudgetExhausted, OpenAlexClient, reconstruct_abstract

BATCH = 800


def load_ontology() -> list[dict]:
    """从 topics.yaml 读取大类+子主题，返回带 topic_id 的分类器结构。"""
    with (config.DATA_DIR / "topics.yaml").open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    slug_to_id = {r["slug"]: r["topic_id"] for r in db.query("SELECT topic_id, slug FROM mining.topics")}
    result = []
    for cat in data["topics"]:
        if "children" not in cat:
            continue
        cat_id = slug_to_id.get(cat["slug"])
        if not cat_id:
            continue
        children = []
        for ch in cat["children"]:
            tid = slug_to_id.get(ch["slug"])
            if tid:
                children.append({
                    "topic_id": tid,
                    "slug": ch["slug"],
                    "name_zh": ch["name_zh"],
                    "query_keywords": ch.get("query_keywords", []),
                    "query_keywords_zh": ch.get("query_keywords_zh", []),
                    "match_keywords": [k.lower() for k in ch.get("match_keywords", [])],
                })
        result.append({
            "topic_id": cat_id,
            "slug": cat["slug"],
            "name_zh": cat["name_zh"],
            "query_keywords": cat.get("query_keywords", []),
            "query_keywords_zh": cat.get("query_keywords_zh", []),
            "match_keywords": [k.lower() for k in cat.get("keywords", [])],
            "children": children,
        })
    return result


def _contains_word(text: str, needle: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", needle):
        return needle in text
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text) is not None


def classify_work(text: str, category: dict) -> list[tuple[int, float]]:
    """返回 [(topic_id, relevance)]，最多 2 个：子主题优先，无命中归大类。"""
    scored = []
    for ch in category["children"]:
        hits = sum(1 for k in ch["match_keywords"] if _contains_word(text, k))
        if hits:
            scored.append((ch["topic_id"], min(0.95, 0.55 + 0.1 * hits)))
    scored.sort(key=lambda x: -x[1])
    if scored:
        return scored[:2]
    cat_hits = sum(1 for k in category["match_keywords"] if _contains_word(text, k))
    if cat_hits:
        return [(category["topic_id"], min(0.7, 0.35 + 0.08 * cat_hits))]
    return [(category["topic_id"], 0.3)]  # 来自该类查询词族，保底归属


_seen_dois: set[str] | None = None


def _doi_available(doi: str | None) -> str | None:
    """不同 OpenAlex 作品可能共用同一 DOI（预印本/正式版），冲突时放弃 doi 入库。"""
    global _seen_dois
    if not doi:
        return None
    if _seen_dois is None:
        _seen_dois = {
            r["doi"] for r in db.query("SELECT doi FROM mining.works WHERE doi IS NOT NULL")
        }
    if doi in _seen_dois:
        return None
    _seen_dois.add(doi)
    return doi


def upsert_work(cur_work: dict) -> int | None:
    title = (cur_work.get("title") or cur_work.get("display_name") or "").strip()
    if not title:
        return None
    abstract = reconstruct_abstract(cur_work.get("abstract_inverted_index"))
    loc = cur_work.get("primary_location") or {}
    source_name = (loc.get("source") or {}).get("display_name") if loc else None
    doi = _doi_available(cur_work.get("doi"))
    row = db.query_one(
        """
        INSERT INTO mining.works
            (openalex_id, doi, title, abstract, work_type, publication_year,
             publication_date, cited_by_count, source_name, lang, raw_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (openalex_id) DO UPDATE
        SET cited_by_count = EXCLUDED.cited_by_count,
            abstract = COALESCE(works.abstract, EXCLUDED.abstract),
            raw_data = EXCLUDED.raw_data
        RETURNING work_id
        """,
        (
            cur_work["id"], doi, title[:600], abstract or None,
            cur_work.get("type"), cur_work.get("publication_year"),
            cur_work.get("publication_date"), cur_work.get("cited_by_count", 0),
            source_name, cur_work.get("language"),
            json.dumps({"referenced_works": cur_work.get("referenced_works", [])}),
        ),
    )
    return row["work_id"]


def build_authorships_cache(authorships: list[dict], work_db_id: int, caches: dict) -> None:
    """抽取作者/机构实体与关系，暂存内存，稍后批量落库。"""
    for pos, auth in enumerate(authorships, start=1):
        author = auth.get("author") or {}
        oa_id = author.get("id")
        if not oa_id:
            continue
        orcid = author.get("orcid")
        if orcid:
            orcid = orcid.rsplit("/", 1)[-1]
        caches["persons"][oa_id] = orcid
        caches["pw"].append((oa_id, work_db_id, pos))

        inst = (auth.get("institutions") or [None])[0]
        if inst and inst.get("id"):
            inst_oa = inst["id"]
            if inst_oa not in caches["institutions"]:
                caches["institutions"].add(inst_oa)
                caches["inst_rows"].append((
                    inst_oa, inst.get("ror"), inst.get("display_name") or "Unknown",
                    inst.get("country_code"), inst.get("type"),
                ))
            caches["pi"].append((oa_id, inst_oa))


def _executemany(sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)


def flush_authorships(caches: dict) -> None:
    """批量写入机构 → 作者 → 关系表。"""
    if caches["inst_rows"]:
        _executemany(
            """
            INSERT INTO mining.institutions (openalex_id, ror_id, name, country_code, institution_type)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (openalex_id) DO NOTHING
            """,
            caches["inst_rows"],
        )
        caches["inst_rows"].clear()

    person_oa_ids = list(caches["persons"].keys())
    for i in range(0, len(person_oa_ids), BATCH):
        chunk = person_oa_ids[i : i + BATCH]
        # orcid 由 enrich 阶段对候选专家安全回填（OpenAlex 存在多实体共用 ORCID 的情况）
        _executemany(
            """
            INSERT INTO mining.persons (openalex_id, display_name)
            VALUES (%s, %s)
            ON CONFLICT (openalex_id) DO NOTHING
            """,
            [(oa, caches["persons_display"].get(oa, "Unknown")) for oa in chunk],
        )

    oa_to_pid = {
        r["openalex_id"]: r["person_id"]
        for r in db.query("SELECT person_id, openalex_id FROM mining.persons WHERE openalex_id = ANY(%s)", (person_oa_ids,))
    }
    inst_map = {
        r["openalex_id"]: r["institution_id"]
        for r in db.query("SELECT institution_id, openalex_id FROM mining.institutions")
    }

    for i in range(0, len(caches["pw"]), BATCH):
        _executemany(
            """
            INSERT INTO mining.person_work (person_id, work_id, author_position)
            VALUES (%s, %s, %s)
            ON CONFLICT (person_id, work_id) DO NOTHING
            """,
            [
                (oa_to_pid[oa], wid, pos)
                for oa, wid, pos in caches["pw"][i : i + BATCH]
                if oa in oa_to_pid
            ],
        )
    for i in range(0, len(caches["pi"]), BATCH):
        _executemany(
            """
            INSERT INTO mining.person_institution (person_id, institution_id, is_current)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (person_id, institution_id) DO NOTHING
            """,
            [
                (oa_to_pid[oa], inst_map[inst_oa])
                for oa, inst_oa in caches["pi"][i : i + BATCH]
                if oa in oa_to_pid and inst_oa in inst_map
            ],
        )
    caches["persons"].clear()
    caches["persons_display"].clear()
    caches["pw"].clear()
    caches["pi"].clear()


def build_citation_edges() -> int:
    """引用边：仅保留两端都在语料内的 cited 关系（PDF 记录 work_citation）。"""
    corpus = {r["openalex_id"]: r["work_id"] for r in db.query("SELECT work_id, openalex_id FROM mining.works")}
    rows = db.query("SELECT work_id, openalex_id, raw_data FROM mining.works WHERE raw_data IS NOT NULL")
    edges = []
    for r in rows:
        refs = (r["raw_data"] or {}).get("referenced_works") or []
        for ref in refs:
            cited_id = corpus.get(ref)
            if cited_id and cited_id != r["work_id"]:
                edges.append((r["work_id"], cited_id))
    for i in range(0, len(edges), BATCH):
        _executemany(
            """
            INSERT INTO mining.work_citation (citing_work_id, cited_work_id)
            VALUES (%s, %s)
            ON CONFLICT (citing_work_id, cited_work_id) DO NOTHING
            """,
            edges[i : i + BATCH],
        )
    return len(edges)


def build_query_list(ontology: list[dict], queries_per_topic: int, zh: bool = False) -> list[tuple[dict, str]]:
    """每子主题取前 N 条查询词、每大类取 1 条；zh=True 时改用中文词族（中文文献语料）。"""
    queries: list[tuple[dict, str]] = []
    for cat in ontology:
        seen_q: set[str] = set()
        if zh:
            for q in cat.get("query_keywords_zh", []):
                if q not in seen_q:
                    seen_q.add(q)
                    queries.append((cat, q))
            for ch in cat["children"]:
                for q in ch.get("query_keywords_zh", [])[:queries_per_topic]:
                    if q not in seen_q:
                        seen_q.add(q)
                        queries.append((cat, q))
        else:
            if cat.get("query_keywords"):
                seen_q.add(cat["query_keywords"][0].lower())
                queries.append((cat, cat["query_keywords"][0]))
            for ch in cat["children"]:
                for q in ch["query_keywords"][:queries_per_topic]:
                    if q.lower() not in seen_q:
                        seen_q.add(q.lower())
                        queries.append((cat, q))
    return queries


def collect(
    max_records_per_query: int | None = None,
    from_year: int | None = None,
    queries_per_topic: int = 1,
    category_slug: str | None = None,
    sort: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    zh: bool = False,
) -> dict:
    """category_slug 用于补采单个大类；sort/from_date 用于"最新论文优先"补采轮。"""
    max_records_per_query = max_records_per_query or config.EXPERT_WORKS_PER_QUERY
    from_year = from_year or config.EXPERT_FROM_YEAR
    ontology = load_ontology()
    if category_slug:
        ontology = [c for c in ontology if c["slug"] == category_slug]
        if not ontology:
            return {"works_collected": 0, "error": f"unknown category {category_slug}"}
    client = OpenAlexClient()

    run = db.query_one(
        "INSERT INTO mining.expert_pipeline_runs (run_type) VALUES ('collect') "
        "RETURNING run_id"
    )

    caches = {
        "persons": {}, "persons_display": {}, "institutions": set(),
        "inst_rows": [], "pw": [], "pi": [],
    }
    queries = build_query_list(ontology, queries_per_topic, zh=zh)
    print(f"collect: {len(queries)} queries over {len(ontology)} categories (zh={zh})")

    new_works, failed = 0, 0
    budget_stop = False
    t0 = time.monotonic()
    for i, (cat, query) in enumerate(queries, start=1):
        if budget_stop:
            break
        try:
            for work in client.works_search(
                query, from_year=from_year, max_records=max_records_per_query,
                sort=sort, from_date=from_date, to_date=to_date,
            ):
                work_db_id = upsert_work(work)
                if work_db_id is None:
                    continue
                text = f"{work.get('title') or ''} {reconstruct_abstract(work.get('abstract_inverted_index'))}".lower()
                for topic_id, rel in classify_work(text, cat):
                    db.execute(
                        "INSERT INTO mining.work_topic (work_id, topic_id, relevance) "
                        "VALUES (%s, %s, %s) ON CONFLICT (work_id, topic_id) DO NOTHING",
                        (work_db_id, topic_id, rel),
                    )
                authorships = work.get("authorships", []) or []
                for pos, auth in enumerate(authorships, start=1):
                    oa_id = (auth.get("author") or {}).get("id")
                    if not oa_id:
                        continue
                    orcid = auth["author"].get("orcid")
                    caches["persons"].setdefault(oa_id, orcid.rsplit("/", 1)[-1] if orcid else None)
                    caches["persons_display"][oa_id] = auth["author"].get("display_name") or "Unknown"
                    caches["pw"].append((oa_id, work_db_id, pos))
                    inst = (auth.get("institutions") or [None])[0]
                    if inst and inst.get("id"):
                        inst_oa = inst["id"]
                        if inst_oa not in caches["institutions"]:
                            caches["institutions"].add(inst_oa)
                            caches["inst_rows"].append((
                                inst_oa, inst.get("ror"), inst.get("display_name") or "Unknown",
                                inst.get("country_code"), inst.get("type"),
                            ))
                        caches["pi"].append((oa_id, inst_oa))
                new_works += 1
        except BudgetExhausted as exc:
            failed += 1
            budget_stop = True
            print(f"[budget] 停止采集 @ query '{query}': {str(exc)[:120]}")
            break
        except Exception as exc:
            failed += 1
            print(f"[fail] query '{query}': {str(exc)[:120]}")
        if i % 10 == 0:
            flush_authorships(caches)
            print(f"  {i}/{len(queries)} queries, +{new_works} works, {time.monotonic() - t0:.0f}s")

    flush_authorships(caches)
    edges = build_citation_edges()
    print(f"collect done: {new_works} works, {edges} citation edges, "
          f"{client.request_count} api calls, {failed} failed queries")

    db.execute(
        """
        UPDATE mining.expert_pipeline_runs
        SET finished_at = now(), works_collected = %s, detail = %s
        WHERE run_id = %s
        """,
        (new_works, json.dumps({"queries": len(queries), "failed": failed,
                                "citation_edges": edges}), run["run_id"]),
    )
    client.close()
    return {"works_collected": new_works, "citation_edges": edges, "failed_queries": failed}
