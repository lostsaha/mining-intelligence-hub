"""固定名册 → OpenAlex 专家实体匹配。

- 每条名册：OpenAlex authors 检索 → 姓氏精确 + 机构/国家校验打分
- 高置信（>=0.7）→ 挂接已有/新建 persons 记录（status=matched）
- 低置信 → 创建无 openalex_id 的独立记录（status=created），算法语料盲区
"""
from __future__ import annotations

import re
import time

import yaml

from .. import config, db
from ..openalex.client import BudgetExhausted, OpenAlexClient

THRESHOLD = 0.7
BATCH_FLUSH = 25


def _tokens(name: str) -> set[str]:
    s = re.sub(r"[.',-]", " ", name.lower())
    return {t for t in s.split() if t}


def match_score(candidate: dict, roster: dict) -> float:
    """严格评分：姓氏 + 名全部对上才算。名字是权威名册，错配比漏配危害大。"""
    roster_tokens = _tokens(roster["name"])
    if not roster_tokens:
        return 0.0
    ordered = roster["name"].lower()
    ordered = [t for t in re.sub(r"[.',-]", " ", ordered).split() if t]
    surname = ordered[-1]                            # 西式名姓在尾
    given_tokens = [t for t in ordered if t != surname]

    variants = {candidate.get("display_name", "")}
    variants.update(candidate.get("display_name_alternatives") or [])

    best_base = 0.0
    best_mode = "last"
    for variant in variants:
        cand_tokens = _tokens(variant)
        if not cand_tokens:
            continue
        # 姓：完整 token（容忍中西名字序）
        surname_ok = (surname in cand_tokens and len(surname) >= 3)
        mode = "last"
        if not surname_ok and ordered[0] in cand_tokens and len(ordered[0]) >= 3 \
                and surname != ordered[0]:
            surname_ok = True   # 名姓颠倒兜底（如 Yuan Liang ↔ Liang Yu）
            mode = "first"
        if not surname_ok:
            continue
        # 名：逐 token 对上（长 token 全等，单字母缩写允许前缀）
        exact = prefix = 0
        for g in given_tokens:
            if g in cand_tokens:
                exact += 1
            elif len(g) == 1 and any(t.startswith(g) for t in cand_tokens):
                prefix += 1
        total = len(given_tokens)
        if total == 0:
            best_base = max(best_base, 0.75)
        elif exact == total:
            best_base = max(best_base, 0.85)
        elif exact + prefix == total:
            best_base = max(best_base, 0.6)
        best_mode = mode
    if best_base == 0.0:
        return 0.0

    score = best_base
    inst_texts = " | ".join(
        (li or {}).get("display_name", "")
        for li in (candidate.get("last_known_institutions") or [])
    )
    affs = " | ".join(
        (a or {}).get("institution", {}).get("display_name", "")
        for a in (candidate.get("affiliations") or [])
    )
    aff = (roster.get("affiliation") or "").lower()
    aff_head = aff.split("(")[0].strip()[:20]
    inst_match = bool(aff_head and (aff_head in (inst_texts + " " + affs).lower()))
    if best_mode == "first" and not inst_match:
        # 名姓颠倒的兜底路径：没有机构佐证时压到阈值以下（宁漏配不错配）
        return min(score, 0.6)
    if inst_match:
        score += 0.1
    if roster.get("country") and candidate.get("country_code") == roster["country"]:
        score += 0.05
    if (candidate.get("works_count") or 0) >= 20:
        score += 0.05
    return min(1.0, score)


def upsert_roster() -> int:
    with (config.DATA_DIR / "admissions.yaml").open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for e in data["entries"]:
        country = e.get("country")
        country = str(country).strip().upper()[:2] if country else None
        db.execute(
            """
            INSERT INTO mining.expert_admissions
                (roster_key, full_name, name_zh, tier, channel, affiliation,
                 country_code, basis)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (roster_key) DO UPDATE
            SET full_name = EXCLUDED.full_name, name_zh = EXCLUDED.name_zh,
                tier = EXCLUDED.tier, channel = EXCLUDED.channel,
                affiliation = EXCLUDED.affiliation, country_code = EXCLUDED.country_code,
                basis = EXCLUDED.basis, updated_at = now()
            """,
            (
                e["key"], e["name"], e.get("name_zh"), e["tier"], e["channel"],
                e.get("affiliation"), country, e["basis"],
            ),
        )
    return len(data["entries"])


def _ensure_person(openalex_id: str | None, display_name: str, orcid: str | None = None) -> int:
    if openalex_id:
        row = db.query_one(
            "SELECT person_id FROM mining.persons WHERE openalex_id = %s", (openalex_id,)
        )
    else:
        row = db.query_one(
            "SELECT person_id FROM mining.persons "
            "WHERE openalex_id IS NULL AND display_name = %s",
            (display_name,),
        )
    if row:
        return row["person_id"]
    row = db.query_one(
        """
        INSERT INTO mining.persons (openalex_id, orcid, display_name)
        VALUES (%s, %s, %s) RETURNING person_id
        """,
        (openalex_id, orcid, display_name),
    )
    return row["person_id"]


def match_pending(client: OpenAlexClient) -> dict:
    entries = db.query(
        """
        SELECT admission_id, roster_key, full_name, name_zh, tier, channel,
               affiliation, country_code, basis
        FROM mining.expert_admissions
        WHERE person_id IS NULL
        ORDER BY admission_id
        """
    )
    matched = created = failed = 0
    for e in entries:
        try:
            data = client.get(
                "/authors",
                {"search": e["full_name"], "per-page": 25,
                 "select": ("id,orcid,display_name,display_name_alternatives,"
                            "last_known_institutions,affiliations,works_count,"
                            "cited_by_count,summary_stats")},
            )
        except BudgetExhausted:
            print(f"[budget] 停止 @ {e['full_name']}")
            failed += 1
            break
        except Exception as exc:
            print(f"[fail] {e['full_name']}: {str(exc)[:100]}")
            failed += 1
            continue

        roster = {"name": e["full_name"], "affiliation": e["affiliation"],
                  "country": e["country_code"]}
        best, best_score = None, 0.0
        for cand in data.get("results", []):
            s = match_score(cand, roster)
            if s > best_score:
                best, best_score = cand, s

        if best and best_score >= THRESHOLD:
            person_id = _ensure_person(best["id"], best["display_name"],
                                       (best.get("orcid") or "").rsplit("/", 1)[-1] or None)
            db.execute(
                """
                UPDATE mining.expert_admissions
                SET person_id = %s, match_status = 'matched',
                    match_confidence = %s, review_note = %s, updated_at = now()
                WHERE admission_id = %s
                """,
                (person_id, round(best_score, 2), f"OpenAlex {best['id']}", e["admission_id"]),
            )
            matched += 1
            print(f"[matched {best_score:.2f}] {e['full_name']} -> {best['display_name']}")
        else:
            note = (f"最佳候选: {best['display_name'] if best else '无'}"
                    f"({best_score:.2f})")
            person_id = _ensure_person(None, e["name_zh"] or e["full_name"])
            db.execute(
                """
                UPDATE mining.expert_admissions
                SET person_id = %s, match_status = 'created',
                    match_confidence = %s, review_note = %s, updated_at = now()
                WHERE admission_id = %s
                """,
                (person_id, round(best_score, 2), note, e["admission_id"]),
            )
            created += 1
            print(f"[created] {e['full_name']} ({note})")
        time.sleep(0.12)
    return {"matched": matched, "created": created, "failed": failed}


def run() -> dict:
    n = upsert_roster()
    print(f"roster synced: {n} entries")
    client = OpenAlexClient()
    try:
        result = match_pending(client)
    finally:
        client.close()
    print(f"match done: {result}")
    return result


if __name__ == "__main__":
    run()
