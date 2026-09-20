"""专家发现与评分（PDF 记录 §18~§25：Seed → Expand → Score → Deduplicate → Curate）。

输入：collect 阶段入库的 Person—Work—Topic—Institution 闭环。
输出：评分后的候选池 + Top 100 专家（含 Coverage Score 多样性、评分历史、证据）。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from .. import config, db
from ..openalex.client import OpenAlexClient

# 与 PDF 记录一致的评分权重（social 未采集，其 10% 分配给 topic_depth）
WEIGHTS = {
    "relevance": 0.35, "impact": 0.20, "activity": 0.15,
    "depth": 0.10, "industry": 0.10, "collab": 0.10,
}
MINING_COMPANY_RE = (
    "rio tinto|bhp|vale|newmont|glencore|anglo american|barrick|freeport|"
    "teck|south32|zijin|紫金|chinalco|alcoa|noront|ivedec|lundin|mining ltd|"
    "minerals ltd|codelco|kgm|mmc norilsk"
)
CURRENT_YEAR = datetime.now(timezone.utc).year


def _log_scale(value: int, ceiling: int) -> float:
    return min(1.0, math.log1p(max(0, value)) / math.log1p(ceiling))


def load_corpus() -> dict:
    works = {
        r["work_id"]: r
        for r in db.query(
            "SELECT work_id, title, publication_year, cited_by_count, work_type FROM mining.works"
        )
    }
    work_topics = defaultdict(list)
    for r in db.query("SELECT work_id, topic_id, relevance FROM mining.work_topic"):
        work_topics[r["work_id"]].append((r["topic_id"], float(r["relevance"] or 0)))
    topics = {
        r["topic_id"]: r
        for r in db.query("SELECT topic_id, slug, name_zh, level, parent_id FROM mining.topics")
    }
    person_work = defaultdict(list)
    for r in db.query("SELECT person_id, work_id FROM mining.person_work"):
        person_work[r["person_id"]].append(r["work_id"])
    persons = {
        r["person_id"]: r
        for r in db.query("SELECT person_id, openalex_id, display_name FROM mining.persons")
    }
    person_inst = defaultdict(list)
    for r in db.query("SELECT person_id, institution_id FROM mining.person_institution"):
        person_inst[r["person_id"]].append(r["institution_id"])
    institutions = {
        r["institution_id"]: r
        for r in db.query(
            "SELECT institution_id, name, country_code, institution_type FROM mining.institutions"
        )
    }
    return {
        "works": works, "work_topics": work_topics, "topics": topics,
        "person_work": person_work, "persons": persons,
        "person_inst": person_inst, "institutions": institutions,
    }


def score_candidates(corpus: dict) -> list[dict]:
    """给每个满足最小作品数的作者打六维分数（纯内存计算）。"""
    works, work_topics, topics = corpus["works"], corpus["work_topics"], corpus["topics"]
    person_work, persons = corpus["person_work"], corpus["persons"]

    # 作品 → 作者（用于合作者网络）
    work_authors = defaultdict(list)
    for pid, wids in person_work.items():
        for wid in wids:
            work_authors[wid].append(pid)

    candidates = []
    for pid, wids in person_work.items():
        wids = list(set(wids))
        if len(wids) < config.EXPERT_MIN_WORKS_PER_AUTHOR:
            continue
        person = persons.get(pid)
        if not person or not person.get("openalex_id"):
            continue

        years = [works[w]["publication_year"] for w in wids if works[w]["publication_year"]]
        citations = sum(works[w]["cited_by_count"] or 0 for w in wids)
        works_5y = sum(1 for w in wids if (works[w]["publication_year"] or 0) >= CURRENT_YEAR - 5)
        works_3y = sum(1 for w in wids if (works[w]["publication_year"] or 0) >= CURRENT_YEAR - 3)
        key_citations = max((works[w]["cited_by_count"] or 0 for w in wids), default=0)

        # 主题画像
        topic_profile = defaultdict(lambda: {"n": 0, "c": 0, "first": 9999, "last": 0, "rel": []})
        child_topic_ids = set()
        rel_sum, rel_n = 0.0, 0
        for w in wids:
            for tid, rel in work_topics.get(w, []):
                tp = topic_profile[tid]
                tp["n"] += 1
                tp["c"] += works[w]["cited_by_count"] or 0
                tp["rel"].append(rel)
                y = works[w]["publication_year"] or 0
                tp["first"] = min(tp["first"], y)
                tp["last"] = max(tp["last"], y)
                rel_sum += rel
                rel_n += 1
                if topics.get(tid, {}).get("level") == 2:
                    child_topic_ids.add(tid)

        # 1) 矿业相关性
        works_with_topic = sum(1 for w in wids if w in work_topics)
        ratio_child = works_with_topic / len(wids)
        avg_rel = (rel_sum / rel_n) if rel_n else 0.0
        coverage = min(1.0, len(child_topic_ids) / 5)
        relevance = 100 * (0.45 * ratio_child + 0.30 * avg_rel + 0.25 * coverage)

        # 2) 学术影响力
        recent_citations = sum(
            works[w]["cited_by_count"] or 0
            for w in wids if (works[w]["publication_year"] or 0) >= CURRENT_YEAR - 5
        )
        impact = 100 * (
            0.45 * _log_scale(citations, 3000)
            + 0.35 * _log_scale(recent_citations, 1200)
            + 0.20 * _log_scale(key_citations, 800)
        )

        # 3) 近期活跃度
        last_year = max(years) if years else 0
        recency = 1.0 if last_year >= CURRENT_YEAR - 1 else 0.7 if last_year >= CURRENT_YEAR - 3 \
            else 0.4 if last_year >= CURRENT_YEAR - 6 else 0.1
        activity = 100 * (
            0.5 * min(1.0, (works_5y / len(wids)) * 1.2)
            + 0.3 * min(1.0, works_3y / 10)
            + 0.2 * recency
        )

        # 4) 主题深度
        shares = [tp["n"] / len(wids) for tp in topic_profile.values()]
        max_share = max(shares) if shares else 0.0
        depth = 100 * (0.7 * min(1.0, len(child_topic_ids) / 6) + 0.3 * max_share)

        # 5) 行业相关（公司型机构 / 矿企名）
        insts = [corpus["institutions"].get(i) for i in corpus["person_inst"].get(pid, [])]
        inst_names = " | ".join((i or {}).get("name") or "" for i in insts).lower()
        has_company = any((i or {}).get("institution_type") == "company" for i in insts)
        industry = 20.0
        if has_company:
            industry += 40
        if re.search(MINING_COMPANY_RE, inst_names):
            industry = 100.0

        # 6) 合作网络
        coauthors = set()
        for w in wids:
            coauthors.update(work_authors.get(w, []))
        coauthors.discard(pid)
        n_insts = len(set(corpus["person_inst"].get(pid, [])))
        collab = 100 * (
            0.7 * _log_scale(len(coauthors), 120) + 0.3 * _log_scale(n_insts, 5)
        )

        expert_score = (
            WEIGHTS["relevance"] * relevance + WEIGHTS["impact"] * impact
            + WEIGHTS["activity"] * activity + WEIGHTS["depth"] * depth
            + WEIGHTS["industry"] * industry + WEIGHTS["collab"] * collab
        )

        # 主类目 = 相关度最高的主题（子主题则回溯其大类）
        top_tid = max(topic_profile, key=lambda t: topic_profile[t]["n"]) if topic_profile else None
        top_topic = topics.get(top_tid) if top_tid else None
        cat_id = top_tid
        if top_topic and top_topic.get("level") == 2:
            cat_id = top_topic["parent_id"]

        candidates.append({
            "person_id": pid, "openalex_id": person["openalex_id"],
            "display_name": person["display_name"],
            "corpus_works": len(wids), "corpus_citations": citations,
            "works_5y": works_5y, "works_3y": works_3y, "first_year": min(years) if years else None,
            "last_year": last_year or None, "coauthor_count": len(coauthors),
            "topic_profile": {t: dict(v) for t, v in topic_profile.items()},
            "top_topic_id": top_tid, "category_id": cat_id,
            "scores": {
                "relevance": round(relevance, 2), "impact": round(impact, 2),
                "activity": round(activity, 2), "depth": round(depth, 2),
                "industry": round(industry, 2), "collab": round(collab, 2),
            },
            "expert_score": round(expert_score, 2),
        })

    # STEP 12：去假阳性（证据门槛：语料内至少 5 篇矿业相关作品）
    candidates = [
        c for c in candidates
        if c["corpus_works"] >= 5
        and c["scores"]["relevance"] >= 35
        and c["expert_score"] >= 30
    ]
    candidates.sort(key=lambda c: -c["expert_score"])
    return candidates[:300]  # 候选池上限（PDF：Top 200~300 参与 enrichment）


def enrich(candidates: list[dict], corpus: dict) -> None:
    """OpenAlex authors 批量补充：ORCID、h-index、国家、当前机构。"""
    client = OpenAlexClient()
    by_oa = {c["openalex_id"]: c for c in candidates}
    all_ids = list(by_oa.keys())
    try:
        for i in range(0, len(all_ids), 25):
            chunk = all_ids[i : i + 25]
            try:
                results = client.authors_batch(chunk)
            except Exception as exc:
                print(f"[warn] enrich batch failed: {str(exc)[:100]}")
                continue
            for auth in results:
                cand = by_oa.get(auth["id"])
                if not cand:
                    continue
                cand["orcid"] = (auth.get("orcid") or "").rsplit("/", 1)[-1] or None
                cand["country_code"] = auth.get("country_code")
                summary = auth.get("summary_stats") or {}
                cand["h_index"] = summary.get("h_index")
                cand["global_works"] = auth.get("works_count")
                last_insts = auth.get("last_known_institutions") or []
                if last_insts:
                    li = last_insts[0]
                    cand["current_inst_oa"] = li.get("id")
                    cand["current_inst_name"] = li.get("display_name")
                    cand["country_code"] = cand.get("country_code") or li.get("country_code")
            print(f"  enriched {min(i + 25, len(all_ids))}/{len(all_ids)}")
    finally:
        client.close()

    # 当前机构入库并关联（is_current 覆盖采集期的"发表时机构"）
    for cand in candidates:
        # ORCID 安全回填：另一 author 实体可能已占用同一 ORCID
        if cand.get("orcid"):
            db.execute(
                """
                UPDATE mining.persons SET orcid = %s
                WHERE person_id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM mining.persons
                      WHERE orcid = %s AND person_id <> %s
                  )
                """,
                (cand["orcid"], cand["person_id"], cand["orcid"], cand["person_id"]),
            )
        oa = cand.get("current_inst_oa")
        if not oa:
            continue
        db.execute(
            """
            INSERT INTO mining.institutions (openalex_id, name, country_code)
            VALUES (%s, %s, %s)
            ON CONFLICT (openalex_id) DO NOTHING
            """,
            (oa, cand.get("current_inst_name") or "Unknown", cand.get("country_code")),
        )
        row = db.query_one(
            "SELECT institution_id FROM mining.institutions WHERE openalex_id = %s", (oa,)
        )
        if row:
            db.execute(
                "UPDATE mining.person_institution SET is_current = FALSE WHERE person_id = %s",
                (cand["person_id"],),
            )
            db.execute(
                """
                INSERT INTO mining.person_institution (person_id, institution_id, is_current)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (person_id, institution_id) DO UPDATE SET is_current = TRUE
                """,
                (cand["person_id"], row["institution_id"]),
            )
            cand["current_institution_id"] = row["institution_id"]


def select_top(candidates: list[dict], top_n: int) -> list[dict]:
    """双层评分：0.70 × Expert Score + 0.30 × Coverage Score（动态多样性）。"""
    topics = {r["topic_id"]: r for r in db.query("SELECT topic_id, parent_id FROM mining.topics")}
    cat_count, inst_count, country_count = Counter(), Counter(), Counter()
    selected: list[dict] = []
    remaining = list(candidates)

    def coverage(c: dict) -> float:
        f = 1.0
        cc = cat_count[c.get("category_id")]
        f *= 0.25 if cc >= 12 else 0.7 if cc >= 6 else 1.0
        if c.get("current_institution_id"):
            ic = inst_count[c["current_institution_id"]]
            f *= 0.6 if ic >= 5 else 0.85 if ic >= 3 else 1.0
        if c.get("country_code"):
            k = country_count[c["country_code"]]
            f *= 0.5 if k >= 25 else 0.8 if k >= 12 else 1.0
        return 100 * f

    while remaining and len(selected) < top_n:
        best, best_score = None, -1.0
        for c in remaining:
            dyn = 0.7 * c["expert_score"] + 0.3 * coverage(c)
            if dyn > best_score:
                best, best_score = c, dyn
        best["coverage_score"] = round(coverage(best), 2)
        best["final_score"] = round(0.7 * best["expert_score"] + 0.3 * best["coverage_score"], 2)
        selected.append(best)
        remaining.remove(best)
        cat_count[best.get("category_id")] += 1
        if best.get("current_institution_id"):
            inst_count[best["current_institution_id"]] += 1
        if best.get("country_code"):
            country_count[best["country_code"]] += 1
    return selected


def key_works_for(cand: dict, corpus: dict) -> dict:
    """代表作品：Key Work Score = 引用百分位 + 主题相关 + 新近度 + 综述加成（PDF §16）。"""
    works = corpus["works"]
    wt = corpus["work_topics"]
    scored = []
    work_ids = [
        r["work_id"]
        for r in db.query(
            "SELECT work_id FROM mining.person_work WHERE person_id = %s", (cand["person_id"],)
        )
    ]
    for wid in work_ids:
        w = works.get(wid)
        if not w:
            continue
        rels = [r for _, r in wt.get(wid, [])] or [0.0]
        year = w["publication_year"] or 0
        kw = (
            0.35 * _log_scale(w["cited_by_count"] or 0, 800)
            + 0.30 * max(rels)
            + 0.20 * (1.0 if year >= CURRENT_YEAR - 4 else 0.4)
            + 0.15 * (1.0 if (w["work_type"] or "") in ("review", "book", "book-chapter") else 0.0)
        )
        scored.append({
            "work_id": wid, "title": w["title"], "year": year,
            "citations": w["cited_by_count"], "key_score": round(kw, 3),
        })
    scored.sort(key=lambda x: -x["key_score"])
    recent = sorted(
        [s for s in scored if s["year"] >= CURRENT_YEAR - 5],
        key=lambda x: -x["citations"],
    )
    return {"classic": scored[:5], "recent": recent[:3]}


def save(selected: list[dict], corpus: dict) -> None:
    today = date.today()
    for rank, cand in enumerate(selected, start=1):
        s = cand["scores"]
        tp = cand["topic_profile"]
        top_names = sorted(tp.items(), key=lambda kv: -kv[1]["n"])[:2]
        topic_names = [corpus["topics"][t]["name_zh"] for t, _ in top_names
                       if t in corpus["topics"]]
        n5 = cand["works_5y"]
        summary = (
            f"长期研究方向以{'、'.join(topic_names) if topic_names else '矿业工程'}为主，"
            f"近5年发表相关论文 {n5} 篇，语料内累计被引 {cand['corpus_citations']} 次"
            + (f"，h-index {cand['h_index']}" if cand.get("h_index") else "")
            + "。"
        )
        db.execute(
            """
            UPDATE mining.persons SET
                orcid = COALESCE(%s, orcid),
                country_code = %s,
                current_institution_id = %s,
                corpus_works = %s, corpus_citations = %s,
                first_year = %s, last_year = %s, coauthor_count = %s,
                mining_relevance_score = %s, research_impact_score = %s,
                recent_activity_score = %s, topic_depth_score = %s,
                industry_score = %s, collaboration_score = %s,
                expert_score = %s, coverage_score = %s, final_score = %s,
                expert_rank = %s, is_selected = TRUE,
                summary_zh = %s,
                raw_data = %s, updated_at = now()
            WHERE person_id = %s
            """,
            (
                cand.get("orcid"), cand.get("country_code"),
                cand.get("current_institution_id"),
                cand["corpus_works"], cand["corpus_citations"],
                cand["first_year"], cand["last_year"], cand["coauthor_count"],
                s["relevance"], s["impact"], s["activity"], s["depth"],
                s["industry"], s["collab"],
                cand["expert_score"], cand["coverage_score"], cand["final_score"],
                rank, summary,
                json.dumps({"h_index": cand.get("h_index"),
                            "global_works": cand.get("global_works")}),
                cand["person_id"],
            ),
        )

        # 人物—主题画像
        db.execute("DELETE FROM mining.person_topic WHERE person_id = %s", (cand["person_id"],))
        for tid, prof in tp.items():
            db.execute(
                """
                INSERT INTO mining.person_topic
                    (person_id, topic_id, relevance, works_count, citation_count,
                     first_year, last_year)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (person_id, topic_id) DO UPDATE
                SET relevance = EXCLUDED.relevance, works_count = EXCLUDED.works_count,
                    citation_count = EXCLUDED.citation_count,
                    first_year = EXCLUDED.first_year, last_year = EXCLUDED.last_year
                """,
                (
                    cand["person_id"], tid,
                    round(sum(prof["rel"]) / len(prof["rel"]), 3) if prof["rel"] else 0.5,
                    prof["n"], prof["c"],
                    prof["first"] if prof["first"] != 9999 else None,
                    prof["last"] or None,
                ),
            )

        # 评分历史（每月重算后对比趋势）
        db.execute(
            """
            INSERT INTO mining.expert_score_history
                (person_id, score_date, mining_relevance_score, research_impact_score,
                 recent_activity_score, topic_depth_score, industry_score,
                 collaboration_score, expert_score, coverage_score, final_score, rank)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cand["person_id"], today,
                s["relevance"], s["impact"], s["activity"], s["depth"],
                s["industry"], s["collab"],
                cand["expert_score"], cand["coverage_score"], cand["final_score"], rank,
            ),
        )

        # 证据：为什么被选中 + 代表作品
        db.execute(
            "DELETE FROM mining.evidence WHERE entity_type = 'person' AND entity_id = %s",
            (cand["person_id"],),
        )
        db.execute(
            """
            INSERT INTO mining.evidence (entity_type, entity_id, evidence_type, claim)
            VALUES ('person', %s, 'selection', %s)
            """,
            (
                cand["person_id"],
                json.dumps({
                    "corpus_works": cand["corpus_works"],
                    "corpus_citations": cand["corpus_citations"],
                    "works_5y": cand["works_5y"],
                    "distinct_topics": len(tp),
                    "score_breakdown": s,
                }, ensure_ascii=False),
            ),
        )
        db.execute(
            """
            INSERT INTO mining.evidence (entity_type, entity_id, evidence_type, claim)
            VALUES ('person', %s, 'key_works', %s)
            """,
            (cand["person_id"], json.dumps(key_works_for(cand, corpus), ensure_ascii=False)),
        )


def build() -> dict:
    run = db.query_one(
        "INSERT INTO mining.expert_pipeline_runs (run_type) VALUES ('build') RETURNING run_id"
    )
    # 重建前清空上一轮榜单标记（跌出 Top N 的专家取消入选）
    db.execute("UPDATE mining.persons SET is_selected = FALSE, expert_rank = NULL WHERE is_selected")
    corpus = load_corpus()
    print(f"corpus: {len(corpus['works'])} works / {len(corpus['person_work'])} authors")
    candidates = score_candidates(corpus)
    print(f"candidates after scoring & filter: {len(candidates)}")

    enrich(candidates, corpus)
    selected = select_top(candidates, config.EXPERT_TOP_N)
    print(f"selected top {len(selected)} experts")
    save(selected, corpus)

    db.execute(
        """
        UPDATE mining.expert_pipeline_runs
        SET finished_at = now(), candidates = %s, selected = %s
        WHERE run_id = %s
        """,
        (len(candidates), len(selected), run["run_id"]),
    )
    return {"candidates": len(candidates), "selected": len(selected)}
