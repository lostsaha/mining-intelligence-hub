"""前沿技术雷达 API：主题论文增速 × 专家聚集度 → 热度排名（PDF 记录 §24 思路）。"""
from __future__ import annotations

from fastapi import HTTPException

from .. import db

SERIES_YEARS = 6


def _topic_rows(level: int) -> list[dict]:
    """每主题：近12月论文数 / 前12月论文数 / 总量 / 近12月引用 / 年度序列 / 专家数。"""
    rows = db.query(
        """
        SELECT t.topic_id, t.slug, t.name_zh, t.name_en, t.parent_id,
               COUNT(wt.work_id) AS total,
               COUNT(wt.work_id) FILTER (
                   WHERE COALESCE(w.publication_date, make_date(w.publication_year, 1, 1))
                         >= CURRENT_DATE - 365
               ) AS w12,
               COUNT(wt.work_id) FILTER (
                   WHERE COALESCE(w.publication_date, make_date(w.publication_year, 1, 1))
                         >= CURRENT_DATE - 730
                     AND COALESCE(w.publication_date, make_date(w.publication_year, 1, 1))
                         < CURRENT_DATE - 365
               ) AS wprev,
               COALESCE(SUM(w.cited_by_count) FILTER (
                   WHERE COALESCE(w.publication_date, make_date(w.publication_year, 1, 1))
                         >= CURRENT_DATE - 365
               ), 0) AS c12
        FROM mining.topics t
        LEFT JOIN mining.work_topic wt ON wt.topic_id = t.topic_id
        LEFT JOIN mining.works w ON w.work_id = wt.work_id
        WHERE t.level = %s
        GROUP BY t.topic_id, t.slug, t.name_zh, t.name_en, t.parent_id
        ORDER BY t.sort_order
        """,
        (level,),
    )

    series: dict[int, dict[int, int]] = {}
    for r in db.query(
        """
        SELECT wt.topic_id, w.publication_year AS yr, COUNT(*) AS n
        FROM mining.work_topic wt
        JOIN mining.works w ON w.work_id = wt.work_id
        WHERE w.publication_year IS NOT NULL
        GROUP BY wt.topic_id, w.publication_year
        """
    ):
        series.setdefault(r["topic_id"], {})[r["yr"]] = r["n"]

    experts: dict[int, dict] = {}
    for r in db.query(
        """
        SELECT ptp.topic_id,
               COUNT(DISTINCT ptp.person_id) AS experts,
               COUNT(DISTINCT ptp.person_id) FILTER (WHERE p.first_year >= %s) AS new_experts
        FROM mining.person_topic ptp
        JOIN mining.persons p ON p.person_id = ptp.person_id
        GROUP BY ptp.topic_id
        """,
        (2024,),
    ):
        experts[r["topic_id"]] = r

    for r in rows:
        yr_series = series.get(r["topic_id"], {})
        if yr_series:
            years = sorted(yr_series)[-SERIES_YEARS:]
            r["yearly"] = [{"year": y, "count": yr_series.get(y, 0)} for y in years]
        else:
            r["yearly"] = []
        r["experts"] = experts.get(r["topic_id"], {}).get("experts", 0)
        r["new_experts"] = experts.get(r["topic_id"], {}).get("new_experts", 0)
    return rows


def _minmax(vals: list[float], v: float) -> float:
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 0.5
    return (v - lo) / (hi - lo)


def _heat(rows: list[dict]) -> list[dict]:
    """热度 = 0.45×增速 + 0.30×近12月产量 + 0.25×专家聚集（组内 min-max 归一）。"""
    w12s = [float(r["w12"]) for r in rows]
    exps = [float(r["experts"]) for r in rows]
    growths = [min(3.0, float(r["w12"]) / max(1.0, float(r["wprev"]))) for r in rows]

    out = []
    for r, growth in zip(rows, growths):
        heat = 100 * (
            0.45 * _minmax(growths, growth)
            + 0.30 * _minmax(w12s, float(r["w12"]))
            + 0.25 * _minmax(exps, float(r["experts"]))
        )

        w12, wprev = float(r["w12"]), float(r["wprev"])
        ratio = w12 / max(1.0, wprev)
        if wprev == 0 and w12 >= 5:
            momentum, momentum_zh = "emerging", "新兴"
        elif w12 < 5 and wprev < 5:
            momentum, momentum_zh = "watch", "观察中"
        elif ratio >= 1.25:
            momentum, momentum_zh = "rising", "快速升温"
        elif ratio >= 0.85:
            momentum, momentum_zh = "steady", "平稳"
        else:
            momentum, momentum_zh = "cooling", "降温"

        out.append({
            **r,
            "growth_ratio": round(ratio, 2),
            "heat": round(heat, 1),
            "momentum": momentum,
            "momentum_zh": momentum_zh,
        })
    out.sort(key=lambda x: -x["heat"])
    return out


def radar(level: int = 2, parent_slug: str | None = None) -> dict:
    rows = _topic_rows(level)
    if parent_slug:
        parent = db.query_one(
            "SELECT topic_id FROM mining.topics WHERE slug = %s", (parent_slug,)
        )
        if not parent:
            raise HTTPException(404, "topic not found")
        rows = [r for r in rows if r["parent_id"] == parent["topic_id"]]
    return {"items": [i for i in _heat(rows) if i["total"] > 0]}
