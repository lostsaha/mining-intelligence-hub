r"""导入 ShowJCR jcr.db（JCR2025 + 中科院分区 FQBJCR2025）→ mining.journal_metrics，
并报告与我们期刊库（works.source_name 去重）的匹配率。
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import db  # noqa: E402

JCR_DB = Path_jcr = r"backend\data\jcr.db"


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (name or "").lower())


def parse_cas(q: str | None) -> str | None:
    """'3 [168/495]' → '3区'; '1 [5/333]' → '1区(Top候选)' 由 Top 列单独给"""
    if not q:
        return None
    m = re.match(r"(\d)", q.strip())
    return f"{m.group(1)}区" if m else q.strip()[:2]


def parse_if(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None  # '<0.1' 等非数值标记


def main() -> int:
    src = sqlite3.connect(JCR_DB)
    sc = src.cursor()

    # JCR2025: IF + JCR 分区（取第一个类目的分区做代表，另存全部类目数）
    jcr = {}
    for journal, issn, eissn, if25, cat, q in sc.execute(
        """SELECT Journal, ISSN, EISSN, [IF(2025)], Category_1, [IF Quartile(2025)_1] FROM JCR2025"""
    ):
        jcr[norm(journal)] = {
            "journal": journal, "issn": issn, "eissn": eissn,
            "if_2025": if25, "jcr_quartile": q, "jcr_category": cat,
        }
    # 中科院分区
    cas = {}
    for journal, year, issn, wos, major, mq, top in sc.execute(
        """SELECT Journal, 年份, [ISSN/EISSN], [Web of Science], 大类, 大类分区, Top FROM FQBJCR2025 WHERE 年份 = 2025"""
    ):
        cas[norm(journal)] = {
            "cas_category": major, "cas_quartile": parse_cas(mq),
            "cas_top": top, "cas_rank": mq,
        }

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS mining.journal_metrics (
            journal       TEXT PRIMARY KEY,
            norm_name     TEXT NOT NULL,
            issn          TEXT,
            eissn         TEXT,
            if_2025       REAL,
            jcr_quartile  TEXT,
            jcr_category  TEXT,
            cas_category  TEXT,
            cas_quartile  TEXT,
            cas_rank      TEXT,
            cas_top       TEXT
        )
        """
    )
    db.execute("DELETE FROM mining.journal_metrics")
    merged = {}
    for k, m in jcr.items():
        merged.setdefault(k, {}).update(m)
    for k, m in cas.items():
        merged.setdefault(k, {}).update(m)
    rows = []
    for k, m in merged.items():
        if not m.get("journal"):
            continue
        rows.append((m.get("journal"), k, m.get("issn"), m.get("eissn"),
                     parse_if(m.get("if_2025")), m.get("jcr_quartile"), m.get("jcr_category"),
                     m.get("cas_category"), m.get("cas_quartile"), m.get("cas_rank"), m.get("cas_top")))
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO mining.journal_metrics
               (journal, norm_name, issn, eissn, if_2025, jcr_quartile, jcr_category,
                cas_category, cas_quartile, cas_rank, cas_top)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows,
        )
    print(f"journal_metrics 导入 {len(rows)} 条")

    # 匹配率对账
    ours = [r["journal"] for r in db.query(
        "SELECT DISTINCT source_name AS journal FROM mining.works WHERE source_name IS NOT NULL AND source_name <> ''")]
    met = {r["norm_name"]: r for r in db.query("SELECT * FROM mining.journal_metrics")}
    hit = [j for j in ours if norm(j) in met]
    print(f"我们的期刊 {len(ours)} 种，直接命中 {len(hit)} ({len(hit) * 100 // max(1, len(ours))}%)")
    miss = [j for j in ours if norm(j) not in met]
    for j in miss[:8]:
        print("  未命中:", j[:60])
    return 0


if __name__ == "__main__":
    sys.exit(main())
