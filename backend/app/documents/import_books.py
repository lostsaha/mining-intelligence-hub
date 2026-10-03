"""自有藏书（H:\00\mining_library\books）导入 documents/versions/chunks。

- 章节骨架以「修复过的中文 EPUB 目录」为权威参照（用户对译本做过大量结构修复），
  英文 MD 分段结果在章节数量量级匹配时按顺序对齐到骨架标题。
- MD 标题结构不可靠（PDF 转换产物），采用自适应分段 + 骨架校正。
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

from .. import db

DEFAULT_ROOT = Path(r"H:\00\mining_library\books")
SKIP_DIRS = {
    "soft", "__pycache__", "papers", "Calibre 书库", "Translatebook",
    "TranslateBook_Data", "mining_epub_work", "zlib", "个人交易研究助手",
    "小学", "矿业聚合平台", "epub_repair_work", "_work", "_work2", "work",
}
CHUNK_TARGET = 1400
CHUNK_MAX = 2200
IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
DETAILS_RE = re.compile(r"<details>.*?</details>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t]+")
_PGNUM_RE = re.compile(r"^(#{1,6})\s+(.+?)\s+\d{1,4}\s*$")
_HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CLEAN_TAIL = re.compile(r"\s*(?:\((?:Z-Library|auth\.)\)|\(Z-Library\))\s*", re.I)


def _cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    return sum(1 for ch in s if "CJK" in unicodedata.name(ch, "")) / max(1, len(s))


def _clean(text: str) -> str:
    text = DETAILS_RE.sub(" ", text)
    text = IMG_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = WS_RE.sub(" ", text)
    return text.strip()


def _split_section(title: str, body: str) -> list[str]:
    body = _clean(body)
    if not body:
        return []
    paras = [p.strip() for p in body.split("\n") if p.strip()]
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


def epub_toc(epub_path: Path):
    """提取中文 EPUB 的章节目录（toc.ncx / nav.xhtml），作为结构权威参照。"""
    try:
        with zipfile.ZipFile(epub_path) as z:
            names = z.namelist()
            toc_file = next((n for n in names if n.endswith("toc.ncx")), None)
            if toc_file:
                xml = z.read(toc_file).decode("utf-8", errors="ignore")
                titles = re.findall(r"<text>([^<]+)</text>", xml)
                titles = [t.strip() for t in titles if t.strip() and len(t.strip()) > 1]
                if len(titles) >= 5:
                    return titles
            nav = next((n for n in names if n.endswith(("nav.xhtml", "toc.xhtml"))), None)
            if nav:
                html = z.read(nav).decode("utf-8", errors="ignore")
                titles = re.findall(r"<a[^>]*>([^<]{2,80})</a>", html)
                titles = [t.strip() for t in titles if t.strip()]
                if len(titles) >= 5:
                    return titles
    except Exception:
        return None
    return None


def _zh_toc_skeleton(titles):
    skip = re.compile(r"封面|版权|目录|扉页|致谢$|Cover|Contents|Copyright", re.I)
    return [t for t in titles if not skip.search(t)]


def parse_markdown(md_path: Path, skeleton):
    """自适应分段 + 中文 EPUB 骨架校正。"""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    lang = "zh" if _cjk_ratio(text[:8000]) > 0.15 else "en"

    lines = text.splitlines()
    boundaries = []
    for i, line in enumerate(lines):
        m = _PGNUM_RE.match(line) or _HEAD_RE.match(line)
        if m:
            title = (m.group(2) or "").strip()
            if 2 < len(title) < 160 and not title.startswith("!"):
                boundaries.append((i, title))

    if len(boundaries) < 3:
        body = _clean("\n".join(lines))
        out = []
        for i in range(0, len(body), CHUNK_TARGET):
            piece = body[i : i + CHUNK_TARGET + 200].strip()
            if len(piece) > 60:
                out.append({"section_path": "(正文窗口)", "content": piece, "lang": lang})
        return out

    sections, pos = [], 0
    for bi, (li, title) in enumerate(boundaries):
        body = "\n".join(lines[pos:li])
        pos = li
        if body.strip():
            sections.append([title, body])
        if bi == len(boundaries) - 1:
            tail = "\n".join(lines[li + 1 :])
            if tail.strip():
                sections.append([title, tail])

    # 骨架校正：章节数量与中文目录同量级时按顺序对齐标题
    if skeleton and 0.33 <= len(skeleton) / max(1, len(sections)) <= 3.0:
        sections = [[skeleton[min(si, len(skeleton) - 1)], body]
                    for si, (title, body) in enumerate(sections)]

    toc_line = re.compile(r"\.{3,}\s*\d{1,4}\s*$|\s\d{1,4}\s*$")
    out = []
    for title, body in sections:
        if re.match(r"^(contents|目录)$", title.strip(), re.I):
            continue  # 目录页整体丢弃
        for piece in _split_section(title, body):
            lines_ = [l for l in piece.split(" ") if l.strip()]
            # 目录特征：大量行以页码结尾（正文窗口按空格合并过，用比例近似）
            tocish = sum(1 for l in lines_ if re.search(r"\d{1,4}$", l.strip()))
            if len(lines_) > 30 and tocish / len(lines_) > 0.4:
                continue
            out.append({"section_path": title, "content": piece, "lang": lang})
    return out


_STD_RE = re.compile(r"^(GB|GBT|GB/T|DZ|AQ|TCSEB|JTG|MT|SL|DB)[\sA-Z]*\d", re.I)


def _classify_dir(d: Path):
    if d.name in SKIP_DIRS or d.name.startswith((".", "_")):
        return None
    files = [f for f in d.iterdir() if f.is_file()]
    if (d.name == "标准" or "标准" in d.name or _STD_RE.match(d.name)
            or any(_STD_RE.match(f.stem) for f in files)):
        return "standard"
    if any(f.suffix.lower() in (".pdf", ".md") for f in files):
        return "book"
    return None


def _version_rows(d: Path):
    pdfs = sorted(d.glob("*.pdf"))
    mds = [p for p in sorted(d.glob("*.md")) if "cleaned" not in p.name.lower()] or sorted(d.glob("*.md"))
    epubs = [p for p in sorted(d.glob("*.epub"))
             if not re.search(r"(demo|backup|fixed|sample)", p.name, re.I)]
    return {
        "pdf": pdfs[0] if pdfs else None,
        "md": mds[0] if mds else None,
        "epub_zh": next((p for p in epubs if re.search(r"[\u4e00-\u9fff]", p.stem)), None),
    }


def import_books(root: Path = DEFAULT_ROOT, limit=None):
    stats = {"books": 0, "versions": 0, "chunks": 0, "failed": 0, "skeleton_aligned": 0}
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        doc_type = _classify_dir(d)
        if not doc_type:
            continue
        if limit and stats["books"] >= limit:
            break
        v = _version_rows(d)
        if not (v["pdf"] or v["md"] or v["epub_zh"]):
            continue

        title_en = re.sub(_CLEAN_TAIL, " ", (v["md"] or v["pdf"] or v["epub_zh"]).stem).strip()
        row = db.query_one(
            """
            INSERT INTO mining.documents (title_en, doc_type, source_dir)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_dir) DO UPDATE SET title_en = EXCLUDED.title_en
            RETURNING document_id
            """,
            (title_en[:300], doc_type, str(d)),
        )
        doc_id = row["document_id"]
        stats["books"] += 1

        skeleton = epub_toc(v["epub_zh"]) if v["epub_zh"] else None
        if skeleton:
            skeleton = _zh_toc_skeleton(skeleton)
            db.execute(
                "UPDATE mining.documents SET title_zh = %s, raw_toc = %s WHERE document_id = %s",
                (skeleton[0] if skeleton else None,
                 json.dumps(skeleton, ensure_ascii=False), doc_id),
            )

        for fmt, lang, path in [("pdf", "en", v["pdf"]), ("md", "en", v["md"]),
                                ("epub", "zh", v["epub_zh"])]:
            if not path:
                continue
            vrow = db.query_one(
                """
                INSERT INTO mining.document_versions
                    (document_id, lang, format, file_path, file_size, parse_status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (file_path) DO UPDATE SET parse_status = 'pending'
                RETURNING version_id, (xmax = 0) AS inserted
                """,
                (doc_id, lang, fmt, str(path), path.stat().st_size),
            )
            version_id = vrow["version_id"]
            if fmt == "md":
                sections = parse_markdown(path, skeleton)
                if len(sections) < 5:
                    db.execute("UPDATE mining.document_versions SET parse_status='failed' WHERE version_id=%s", (version_id,))
                    stats["failed"] += 1
                    print(f"  [warn] {path.name[:40]} 分段过少({len(sections)}) -> failed")
                    stats["versions"] += 1
                    continue
                db.execute("DELETE FROM mining.document_chunks WHERE version_id=%s", (version_id,))
                with db.get_conn() as conn, conn.cursor() as cur:
                    for idx, sec in enumerate(sections):
                        cur.execute(
                            """
                            INSERT INTO mining.document_chunks
                                (document_id, version_id, lang, chunk_index, section_path, content, char_count)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (doc_id, version_id, sec["lang"], idx,
                             sec["section_path"][:300], sec["content"], len(sec["content"])),
                        )
                stats["chunks"] += len(sections)
                if skeleton and 0.33 <= len(skeleton) / max(1, len(sections)) <= 3.0:
                    stats["skeleton_aligned"] += 1
                db.execute("UPDATE mining.document_versions SET parse_status='parsed' WHERE version_id=%s", (version_id,))
            else:
                db.execute("UPDATE mining.document_versions SET parse_status='skipped' WHERE version_id=%s", (version_id,))
            stats["versions"] += 1
        print(f"[book] {title_en[:56]} ({doc_type}) skeleton={'Y' if skeleton else '-'}")
    return stats


if __name__ == "__main__":
    root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else DEFAULT_ROOT
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(import_books(root=root, limit=lim))
