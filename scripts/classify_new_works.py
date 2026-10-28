r"""新入库 964 篇按类型甄别：书籍/学位论文/论文集/会议论文/期刊论文。
书籍 md 移入 mineru_results\Book\ 并登记 mining.documents(doc_type='book')+version。
输出完整清单供用户知晓。用法：python classify_new_works.py [--go]
"""
import re
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import db  # noqa: E402

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
CANON = Path(r"H:\00\zotero\mineru_results")
CJK = re.compile(r"[\u4e00-\u9fff]")
PROC_RE = re.compile(r"proceedings|symposium|会议论文集|文集|Special Issue Reprint", re.I)
THEsis_RE = re.compile(r"thesis|dissertation|学位论文|graduate school", re.I)


def main() -> int:
    go = "--go" in sys.argv
    # Zotero itemType 反查表：附件 basename → 父条目类型
    zconn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=30)
    zc = zconn.cursor()
    zc.execute("""SELECT a.path, it.typeName FROM itemAttachments a
                  JOIN items ai ON ai.itemID = a.itemID
                  LEFT JOIN items pi ON pi.itemID = a.parentItemID
                  LEFT JOIN itemTypes it ON it.itemTypeID = pi.itemTypeID
                  WHERE a.contentType='application/pdf'
                  AND a.itemID NOT IN (SELECT itemID FROM deletedItems)""")
    ztype = {}
    for path, tname in zc.fetchall():
        if not path:
            continue
        bn = path.replace("storage:", "").replace("file://", "").replace("/", "\\").split("\\")[-1]
        ztype[bn] = tname or ""
    zconn.close()

    rows = db.query(
        """
        SELECT w.work_id, w.title, MIN(c.md_source) AS md_source, COUNT(c.chunk_id) AS chunks
        FROM mining.works w JOIN mining.work_chunks c ON c.work_id = w.work_id
        WHERE w.source_name = '本地解析/Zotero' AND w.created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY w.work_id, w.title
        """
    )
    print(f"待甄别新入库论文: {len(rows)}\n")
    counts = {"Book": 0, "学位论文": 0, "论文集": 0, "会议论文": 0, "期刊论文": 0}
    books, cats = [], {c: [] for c in counts}
    for r in rows:
        name = Path(r["md_source"]).name if r["md_source"] else ""
        zt = ztype.get(name, "")
        hay = f"{name} {r['title']}"
        if zt in ("book", "bookSection") or re.search(r"handbook|手册|Handbook|Encyclopedia", hay):
            cat, why = "Book", f"Zotero:{zt}" if zt in ("book", "bookSection") else "标题关键词"
        elif zt == "thesis" or THEsis_RE.search(hay):
            cat, why = "学位论文", f"Zotero:{zt}" if zt == "thesis" else "标题关键词"
        elif PROC_RE.search(hay) and r["chunks"] > 150:
            cat, why = "论文集", "proceedings 特征+大篇幅"
        elif zt == "conferencePaper" or re.search(r"conference|proceedings|symposium|会议", hay, re.I):
            cat, why = "会议论文", f"Zotero:{zt}" if zt == "conferencePaper" else "标题特征"
        else:
            cat, why = "期刊论文", f"Zotero:{zt}" if zt else "默认"
        counts[cat] += 1
        cats[cat].append((r["work_id"], r["title"], r["md_source"], r["chunks"], why))
        if cat == "Book":
            books.append((r["work_id"], r["title"], r["md_source"], r["chunks"], why))

    print("== 分类结果 ==")
    for c, n in counts.items():
        print(f"  {c}: {n}")
    print("\n== Book 候选明细 ==")
    for wid, t, ms, ch, why in books:
        print(f"  [{wid}] {ch:4d}段 | {ms[-52:] if ms else '(无md)'} | {t[:44]}")

    if not go:
        print("\n[dry] 加 --go 执行：书籍 md 移入 Book\\ 并登记 documents")
        return 0

    print("\n== 执行：书籍移入 Book\\ + 登记 ==")
    for wid, t, ms, ch, why in books:
        if not ms or not Path(ms).exists():
            print(f"  [跳过无md] {t[:44]}")
            continue
        src = Path(ms)
        dst_dir = CANON / "Book"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.move(str(src), str(dst))
            db.execute("UPDATE mining.work_chunks SET md_source = %s WHERE work_id = %s", (str(dst), wid))
        sdir = str(dst.parent)
        doc = db.query_one(
            """INSERT INTO mining.documents (title_en, doc_type, source_dir, access_status)
               VALUES (%s, 'book', %s, 'private-owned')
               ON CONFLICT (source_dir) DO UPDATE SET title_en = EXCLUDED.title_en
               RETURNING document_id""",
            (t[:300], sdir),
        )
        did = doc["document_id"]
        db.query_one(
            """INSERT INTO mining.document_versions
               (document_id, lang, format, file_path, file_size, parse_status)
               VALUES (%s, %s, 'md', %s, %s, 'parsed')
               ON CONFLICT (file_path) DO UPDATE SET parse_status='parsed'
               RETURNING version_id""",
            (did, "zh" if CJK.search(t) else "en", str(dst), dst.stat().st_size),
        )
        print(f"  [登记 doc={did}] {t[:48]} → Book\\")
    return 0


if __name__ == "__main__":
    sys.exit(main())
