r"""为未匹配的解析 md 建档：先查 Zotero（链接/存储附件按文件名对应），无则从文件名解析。
建档规则：title 去重（norm 前 60）；DOI 重复置空；source_name 标注来源。
完成后重跑 import_paper_md 即可分段。
用法：python create_missing_works.py [--go]
"""
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import db  # noqa: E402
from app.documents.find_unparsed import _norm as _norm_title, _title_after_year  # noqa: E402

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
MD_AREAS = [
    Path(r"H:\00\zotero\mineru_results"),
    Path(r"H:\00\zotero\all_md"),
]
YEAR_RE = re.compile(r"(19|20)\d{2}")


def parse_name(stem: str) -> tuple[str, int | None, str]:
    """"Author 等 - 2015 - Title" / "Title_2023" → (title, year, author_hint)"""
    s = stem.replace("_", " - ").strip()
    m = re.match(r"^(.{1,60}?)\s+-\s+((?:19|20)\d{2})\s+-\s+(.+)$", s)
    if m:
        return m.group(3).strip(), int(m.group(2)), m.group(1).strip()
    m2 = re.match(r"^(.+?)\s+((?:19|20)\d{2})\s*[-_]", s)
    if m2:
        return s, int(m2.group(2)), m2.group(1)
    y = YEAR_RE.search(s)
    return s, (int(y.group(0)) if y else None), ""


def main() -> int:
    go = "--go" in sys.argv
    # 现有 works 键
    existing = {_norm_title(r["title"])[:60] for r in db.query("SELECT title FROM mining.works WHERE title IS NOT NULL")}
    existing_doi = {re.sub(r"[^0-9a-z]", "", (r["doi"] or "").lower()) for r in db.query("SELECT doi FROM mining.works WHERE doi IS NOT NULL")}
    # MD 候选（与 import_paper_md 同源），找未匹配的
    cur = db.cursor() if False else None
    by_title = {_norm_title(r["title"])[:60]: r["work_id"] for r in db.query("SELECT work_id, title FROM mining.works WHERE title IS NOT NULL")}

    zconn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=30)
    zc = zconn.cursor()
    zc.execute("""SELECT a.path, COALESCE(pt.value,''), COALESCE(pi.dateAdded,''),
                  COALESCE(dv.value,'') FROM itemAttachments a
                  JOIN items ai ON ai.itemID = a.itemID
                  LEFT JOIN items pi ON pi.itemID = a.parentItemID
                  LEFT JOIN itemData pd ON pd.itemID = a.parentItemID
                       AND pd.fieldID = (SELECT fieldID FROM fields WHERE fieldName='title')
                  LEFT JOIN itemDataValues pt ON pt.valueID = pd.valueID
                  LEFT JOIN itemData dd ON dd.itemID = a.parentItemID
                       AND dd.fieldID = (SELECT fieldID FROM fields WHERE fieldName='date')
                  LEFT JOIN itemDataValues dv ON dv.valueID = dd.valueID
                  WHERE a.contentType='application/pdf'
                  AND a.itemID NOT IN (SELECT itemID FROM deletedItems)""")
    zmap = {}
    for path, ptitle, pdate, _doi in zc.fetchall():
        if not path:
            continue
        bn = path.replace("storage:", "").replace("file://", "").replace("/", "\\").split("\\")[-1]
        zmap[bn] = (ptitle, pdate)
    zconn.close()

    created = skipped_parsed = skipped_doi = 0
    for area in MD_AREAS:
        if not area.exists():
            continue
        for md in sorted(area.rglob("*.md")):
            stem = md.stem
            nt = _norm_title(stem)[:60]
            if nt in existing or nt in by_title:
                continue
            # Zotero 元数据优先
            zt, zd = zmap.get(md.name, ("", ""))
            title, year, author = (zt, None, "") if zt else parse_name(stem)
            if zt and zd:
                ym = YEAR_RE.search(zd)
                year = int(ym.group(0)) if ym else None
            if not title or len(title) < 8:
                continue
            k = _norm_title(title)[:60]
            if k in existing or k in by_title:
                continue
            doi = None  # 不从文件名猜 DOI，避免脏数据
            if not go:
                created += 1
                continue
            r = db.query_one(
                """INSERT INTO mining.works
                   (title, publication_year, doi, source_name, lang, work_type, is_open_access)
                   VALUES (%s, %s, %s, '本地解析/Zotero', %s, 'article', false)
                   RETURNING work_id""",
                (title[:500], year, doi,
                 "zh" if re.search(r"[\u4e00-\u9fff]", title) else "en"),
            )
            existing.add(k)
            created += 1
    print(f"{'[dry] ' if not go else ''}建档 {created} 篇")
    if not go:
        print("加 --go 执行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
