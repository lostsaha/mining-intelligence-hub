"""Zotero 个人文库导入（只读 zotero.sqlite，不写原库）。

- 条目（期刊/会议论文）→ mining.works（source_name='Zotero 个人文库'）
- DOI 与既有 OpenAlex 语料去重：命中则把标签并入既有 works.raw_data，不重复插入
- 中文标签（#露天矿 等）存入 raw_data.zotero_tags —— 用户人工标注 = 金标准主题线索
- PDF 附件路径存 raw_data.pdf_path，供后续 PyMuPDF 分段（页码级证据）
- 用法：python -m app.documents.import_zotero [--zotero "E:/Zotero/zotero.sqlite"]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

from .. import db

DEFAULT_DB = Path(r"E:\Zotero\zotero.sqlite")


def _cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for ch in s if "CJK" in unicodedata.name(ch, "")) / max(1, len(s))


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (t or "").lower())


import re  # noqa: E402


def fetch_items(zotero_path: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{zotero_path.as_posix()}?mode=ro", uri=True)
    cur = conn.cursor()
    items: dict[int, dict] = {}

    cur.execute(
        """
        SELECT i.itemID, f.fieldName, COALESCE(v.value, '')
        FROM items i
        JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        JOIN itemData d ON d.itemID = i.itemID
        JOIN fields f ON f.fieldID = d.fieldID
        LEFT JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE it.typeName IN ('journalArticle', 'conferencePaper', 'preprint', 'thesis', 'report')
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    for item_id, field, value in cur.fetchall():
        it = items.setdefault(item_id, {"title": "", "doi": "", "journal": "", "date": "", "abstract": ""})
        if field == "title" and not it["title"]:
            it["title"] = value
        elif field == "DOI" and not it["doi"]:
            it["doi"] = value.strip()
        elif field == "publicationTitle" and not it["journal"]:
            it["journal"] = value
        elif field == "date" and not it["date"]:
            it["date"] = value
        elif field == "abstractNote" and not it["abstract"]:
            it["abstract"] = value

    # 标签
    cur.execute(
        """
        SELECT it.itemID, z.name FROM itemTags it
        JOIN tags z ON z.tagID = it.tagID
        WHERE it.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    for item_id, tag in cur.fetchall():
        if item_id in items:
            items[item_id].setdefault("tags", []).append(tag)

    # PDF 附件路径
    cur.execute(
        """
        SELECT a.parentItemID, ai.key, a.path FROM itemAttachments a
        JOIN items ai ON ai.itemID = a.itemID
        JOIN items i ON i.itemID = a.parentItemID
        WHERE a.contentType = 'application/pdf'
          AND a.linkMode = 0
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    for parent_id, key, path in cur.fetchall():
        if parent_id in items and path:
            fname = path.replace("storage:", "")
            items[parent_id]["pdf_path"] = f"E:/Zotero/storage/{key}/{fname}"
    conn.close()

    out = []
    for it in items.values():
        if it["title"] and it["title"].strip():
            out.append(it)
    return out


def _load_existing_index() -> dict:
    """预载 DOI→work_id 与 标题规范形→work_id 映射（避免逐条全表比对）。"""
    doi_map, title_map = {}, {}
    for r in db.query("SELECT work_id, doi, title FROM mining.works"):
        if r["doi"]:
            doi_map[r["doi"].lower()] = r["work_id"]
        nt = _norm_title(r["title"])
        if nt and nt not in title_map:
            title_map[nt] = r["work_id"]
    return {"doi": doi_map, "title": title_map}


def _match_existing(doi: str, title_norm: str, index: dict):
    if doi:
        hit = index["doi"].get(doi.lower()) or index["doi"].get(
            f"https://doi.org/{doi}".lower())
        if hit:
            return hit
    return index["title"].get(title_norm)


def import_zotero(zotero_path: Path = DEFAULT_DB, limit: int | None = None) -> dict:
    items = fetch_items(zotero_path)
    if limit:
        items = items[:limit]
    stats = {"items": len(items), "inserted": 0, "merged_doi": 0,
             "merged_title": 0, "with_pdf": 0, "skipped": 0}
    index = _load_existing_index()
    for it in items:
        title = it["title"].strip()
        doi = it["doi"].strip()
        if not title:
            stats["skipped"] += 1
            continue
        title_norm = _norm_title(title)

        existing = _match_existing(doi, title_norm, index)
        tags = [t for t in it.get("tags", []) if not t.startswith(("📖", "_", "/", "#Y-"))]
        pdf_path = it.get("pdf_path")
        if pdf_path and Path(pdf_path).exists():
            stats["with_pdf"] += 1

        year = 0
        m = re.search(r"(19|20)\d{2}", it.get("date", ""))
        if m:
            year = int(m.group(0))

        if existing:
            # 既有语料命中：合并标签与 PDF 路径（不重复插论文）
            merge = {}
            if tags:
                merge["zotero_tags"] = tags
            if pdf_path:
                merge["pdf_path"] = pdf_path
            if merge:
                db.execute(
                    "UPDATE mining.works SET raw_data = COALESCE(raw_data,'{}'::jsonb) || %s WHERE work_id = %s",
                    (json.dumps(merge, ensure_ascii=False), existing),
                )
            if it["doi"]:
                stats["merged_doi"] += 1
            else:
                stats["merged_title"] += 1
            continue

        lang = "zh" if _cjk_ratio(title) > 0.15 else "en"
        db.execute(
            """
            INSERT INTO mining.works
                (doi, title, abstract, work_type, publication_year,
                 cited_by_count, source_name, lang, raw_data)
            VALUES (%s, %s, %s, 'paper', %s, 0, 'Zotero 个人文库', %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                (doi if doi.startswith("http") else f"https://doi.org/{doi}") if doi else None,
                title[:600],
                it.get("abstract") or None,
                year or None,
                lang,
                json.dumps({
                    "origin": "zotero",
                    "journal": it.get("journal"),
                    "zotero_tags": tags,
                    **({"pdf_path": pdf_path} if pdf_path else {}),
                }, ensure_ascii=False),
            ),
        )
        stats["inserted"] += 1
    return stats


if __name__ == "__main__":
    zdb = Path(sys.argv[sys.argv.index("--zotero") + 1]) if "--zotero" in sys.argv else DEFAULT_DB
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(import_zotero(zotero_path=zdb, limit=lim))
