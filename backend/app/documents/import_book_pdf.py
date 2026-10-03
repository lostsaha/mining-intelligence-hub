"""PDF-only 书籍解析：PyMuPDF 逐页提取 → 页码级分段入库 document_chunks。

- section_path 优先取 PDF 书签目录（doc.get_toc()，页码对齐）；无书签回退"第 N 页"
- 每页清洗后按 CHUNK_TARGET 窗口合并成段，保留 page_start/page_end 供 /ask 引用
- 用法：python -m app.documents.import_book_pdf [--limit N]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

from .. import db
from .import_books import _classify_dir, _version_rows

CHUNK_TARGET = 1400
CHUNK_MAX = 2200
_HYPHEN_RE = re.compile(r"(\w)-\n(\w)")  # 英文换行连字
_WS_RE = re.compile(r"[ \t]+")
_NUL_RE = re.compile(r"\x00+")  # PDF 内嵌字体常吐 NUL，PostgreSQL 拒收


def _clean_page(text: str) -> str:
    text = _NUL_RE.sub("", text)
    text = _HYPHEN_RE.sub(r"\1\2", text)
    text = re.sub(r"<details>.*?</details>", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _window_chunks(text: str) -> list[str]:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > CHUNK_TARGET and buf:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf} {p}".strip()
    if buf:
        chunks.append(buf)
    final = []
    for c in chunks:
        while len(c) > CHUNK_MAX:
            cut = max(c.rfind("。", 0, CHUNK_MAX), c.rfind(". ", 0, CHUNK_MAX)) or CHUNK_MAX
            final.append(c[:cut].strip())
            c = c[cut:].strip()
        if len(c) > 60:
            final.append(c)
    return final


def _toc_for_pages(doc) -> dict[int, str]:
    """PDF 书签 → {页码(1-based): 最近的层级标题链}。"""
    try:
        toc = doc.get_toc()
    except Exception:
        toc = []
    if not toc:
        return {}
    pages: dict[int, list[str]] = {}
    chain: dict[int, str] = {}
    for level, title, page in toc:
        chain[level] = title.strip()
        deeper = [k for k in chain if k > level]
        for k in deeper:
            chain.pop(k, None)
        chain_str = " / ".join(chain[l] for l in sorted(chain))
        pages[page] = chain_str
    last = ""
    out = {}
    for p in range(1, (doc.page_count or 0) + 1):
        if p in pages:
            last = pages[p]
        out[p] = last
    return out


def import_book_pdf(limit: int | None = None) -> dict:
    stats = {"books": 0, "pages": 0, "chunks": 0, "skipped": 0}
    root = Path(r"H:\00\mining_library\books")
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if _classify_dir(d) is None:
            continue
        if limit and stats["books"] >= limit:
            break
        v = _version_rows(d)
        if not v["pdf"]:
            continue
        docrow = db.query_one(
            "SELECT document_id FROM mining.documents WHERE source_dir = %s", (str(d),)
        )
        if not docrow:
            continue  # 只补已登记书籍
        doc_id = docrow["document_id"]

        # 已有 MD 分段的跳过（MD 优先，PDF 补页码级证据留给需要时）
        have = db.query_one(
            "SELECT COUNT(*) AS n FROM mining.document_chunks WHERE document_id=%s", (doc_id,)
        )["n"]
        if have > 0:
            stats["skipped"] += 1
            continue
        vrow = db.query_one(
            "SELECT version_id FROM mining.document_versions WHERE document_id=%s AND format='pdf'",
            (doc_id,),
        )
        if not vrow:
            continue

        pdf_path = Path(v["pdf"])
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as exc:
            print(f"[fail] {pdf_path.name[:40]}: {str(exc)[:80]}")
            db.execute("UPDATE mining.document_versions SET parse_status='failed' WHERE version_id=%s", (vrow["version_id"],))
            stats["books"] += 1
            continue

        toc_map = _toc_for_pages(doc)
        sections: list[tuple[str, int, int]] = []  # (section, page_start, page_end)
        buf, buf_start, cur_sec = "", 0, ""
        n_pages = doc.page_count or 0
        for pno in range(n_pages):
            page_text = _clean_page(doc[pno].get_text("text") or "")
            sec = toc_map.get(pno + 1, "")
            if sec and sec != cur_sec and buf.strip():
                sections.append((cur_sec or f"p{buf_start}", buf, buf_start, pno - 1))
                buf, buf_start = "", pno + 1
            cur_sec = sec or cur_sec or f"p{pno + 1}"
            if not buf:
                buf_start = pno + 1
            buf = f"{buf} {page_text}".strip()
            if len(buf) >= CHUNK_TARGET:
                sections.append((cur_sec, buf, buf_start, pno + 1))
                buf, buf_start = "", pno + 2
        if buf.strip():
            sections.append((cur_sec, buf, buf_start, n_pages))
        doc.close()

        db.execute("DELETE FROM mining.document_chunks WHERE version_id=%s", (vrow["version_id"],))
        idx = 0
        with db.get_conn() as conn, conn.cursor() as cur:
            for sec, body, p1, p2 in sections:
                for piece in _window_chunks(body):
                    cur.execute(
                        """
                        INSERT INTO mining.document_chunks
                            (document_id, version_id, lang, chunk_index, section_path,
                             content, char_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (doc_id, vrow["version_id"], "en", idx,
                         f"{sec} [p{p1}-{p2}]"[:300], piece, len(piece)),
                    )
                    idx += 1
        stats["chunks"] += idx
        stats["pages"] += n_pages
        stats["books"] += 1
        db.execute("UPDATE mining.document_versions SET parse_status='parsed' WHERE version_id=%s", (vrow["version_id"],))
        print(f"[pdf-book] {pdf_path.name[:48]}: {n_pages} 页 → {idx} 段")
    return stats


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(import_book_pdf(limit=lim))
