"""中文译本 EPUB 正文分段入库 document_chunks（补 4C 缺口）。

此前 EPUB 只登记版本 + 用作目录骨架参照，正文未分段（/ask 检索不到译文）。
本导入器按 EPUB 自身结构（OPF spine 章节顺序）抽取正文，
章节标题优先取 xhtml 内部标题，回退 toc.ncx/nav 目录标题。
用法：python -m app.documents.import_epub_chunks [--limit N]
"""
from __future__ import annotations

import html
import re
import sys
import zipfile
from pathlib import Path

from .. import db
from .import_books import _cjk_ratio, _split_section, _zh_toc_skeleton, epub_toc

_SKIP_ITEM = re.compile(r"封面|版权|目录|扉页|Cover|Contents|Copyright|toc", re.I)


def _spine_hrefs(z: zipfile.ZipFile) -> list[str]:
    """OPF spine → 按阅读顺序的 xhtml 文件路径列表。"""
    container = z.read("META-INF/container.xml").decode("utf-8", errors="ignore")
    m = re.search(r'full-path="([^"]+)"', container)
    if not m:
        return []
    opf_path = m.group(1)
    opf = z.read(opf_path).decode("utf-8", errors="ignore")
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    items: dict[str, tuple[str, str]] = {}
    for tag in re.findall(r"<item\b[^>]*>", opf):
        mid = re.search(r'id="([^"]+)"', tag)
        mhref = re.search(r'href="([^"]+)"', tag)
        mtype = re.search(r'media-type="([^"]+)"', tag)
        if mid and mhref:
            items[mid.group(1)] = (mhref.group(1), mtype.group(1) if mtype else "")
    out = []
    for idref in re.findall(r'<itemref\b[^>]*idref="([^"]+)"', opf):
        if idref not in items:
            continue
        href, mtype = items[idref]
        if mtype.endswith("html") or href.lower().endswith((".xhtml", ".html")):
            out.append(base + href.lstrip("./"))
    return out


def _xhtml_text(raw: str) -> tuple[str | None, str]:
    """xhtml → (首标题, 正文文本)。块级标签转换行，保留段落结构。"""
    raw = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
    title = None
    mh = re.search(r"<h([1-6])\b[^>]*>(.*?)</h\1>", raw, flags=re.S | re.I)
    if mh:
        t = re.sub(r"<[^>]+>", " ", mh.group(2))
        title = re.sub(r"\s+", " ", html.unescape(t)).strip() or None
    body = re.sub(r"<(p|div|br|h[1-6]|li|tr|td)\b[^>]*>", "\n", raw, flags=re.I)
    body = re.sub(r"<[^>]+>", "", body)
    body = html.unescape(body)
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in body.splitlines()]
    return title, "\n".join(ln for ln in lines if ln)


def _chapter_title(heading: str | None, toc_titles: list[str], toc_ptr: list[int], k: int) -> str:
    if heading and 1 < len(heading) < 120:
        return heading
    while toc_ptr[0] < len(toc_titles):
        t = toc_titles[toc_ptr[0]]
        toc_ptr[0] += 1
        if not _SKIP_ITEM.search(t):
            return t
    return f"第{k}节"


def epub_chunks(epub_path: Path) -> list[dict]:
    """EPUB → [{section_path, content, lang}]，按 spine 章节切。"""
    toc_titles = _zh_toc_skeleton(epub_toc(epub_path) or [])
    chapters: list[tuple[str, str]] = []
    with zipfile.ZipFile(epub_path) as z:
        toc_ptr = [0]
        for k, href in enumerate(_spine_hrefs(z), 1):
            try:
                raw = z.read(href).decode("utf-8", errors="ignore")
            except KeyError:
                continue
            heading, text = _xhtml_text(raw)
            if len(text) < 200 or (heading and _SKIP_ITEM.search(heading)):
                continue  # 封面/版权/空页
            title = _chapter_title(heading, toc_titles, toc_ptr, len(chapters) + 1)
            chapters.append((title, text))

    lang = "zh" if _cjk_ratio("".join(t for _, t in chapters)[:8000]) > 0.15 else "en"
    out: list[dict] = []
    for title, text in chapters:
        for piece in _split_section(title, text):
            out.append({"section_path": title, "content": piece, "lang": lang})
    return out


def import_epub_chunks(limit: int | None = None) -> dict:
    stats = {"books": 0, "chunks": 0, "skipped": 0, "failed": 0}
    rows = db.query(
        """
        SELECT v.version_id, v.file_path, d.document_id,
               COALESCE(d.title_zh, d.title_en) AS title
        FROM mining.document_versions v
        JOIN mining.documents d USING (document_id)
        WHERE v.format = 'epub' AND (v.parse_status IS DISTINCT FROM 'parsed')
        ORDER BY d.document_id
        """
    )
    for r in rows:
        if limit and stats["books"] >= limit:
            break
        path = Path(r["file_path"])
        if not path.exists():
            print(f"[missing] {str(r['title'])[:40]}: {path.name[:50]}")
            stats["failed"] += 1
            continue
        try:
            sections = epub_chunks(path)
        except Exception as exc:
            print(f"[fail] {path.name[:44]}: {str(exc)[:80]}")
            db.execute(
                "UPDATE mining.document_versions SET parse_status='failed' WHERE version_id=%s",
                (r["version_id"],),
            )
            stats["failed"] += 1
            continue
        if len(sections) < 5:
            print(f"[warn] {path.name[:44]} 分段过少({len(sections)}) -> failed")
            db.execute(
                "UPDATE mining.document_versions SET parse_status='failed' WHERE version_id=%s",
                (r["version_id"],),
            )
            stats["failed"] += 1
            continue
        db.execute("DELETE FROM mining.document_chunks WHERE version_id=%s", (r["version_id"],))
        with db.get_conn() as conn, conn.cursor() as cur:
            for idx, sec in enumerate(sections):
                cur.execute(
                    """
                    INSERT INTO mining.document_chunks
                        (document_id, version_id, lang, chunk_index, section_path, content, char_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (r["document_id"], r["version_id"], sec["lang"], idx,
                     sec["section_path"][:300], sec["content"], len(sec["content"])),
                )
        db.execute(
            "UPDATE mining.document_versions SET parse_status='parsed' WHERE version_id=%s",
            (r["version_id"],),
        )
        stats["chunks"] += len(sections)
        stats["books"] += 1
        print(f"[epub] {str(r['title'])[:44]}: {len(sections)} 段 ({sections[0]['lang']})")
    return stats


if __name__ == "__main__":
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(import_epub_chunks(limit=lim))
