"""Zotero 解析 MD（H:\00\zotero）→ work_chunks 批量导入。

匹配：MD 文件名里的 Zotero 式标题段 → 与 works.raw_data.pdf_path 的文件名 /
works 标题规范形匹配。未匹配的 MD 跳过并计数（可先建 works 再重跑）。
用法：python -m app.documents.import_paper_md [--root "H:/00/zotero"]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .. import db
from .import_books import _clean, _cjk_ratio, _split_section

DEFAULT_ROOT = Path(r"H:\00\zotero")
CHUNK_TARGET = 1200
CHUNK_MAX = 2000
# PostgreSQL text 拒收 NUL/控制字符；MinerU 输出偶有。
# 转义写在普通字符串里（"\\x00"），Python 编译后即 \x00 控制符语义。
_NUL_RE = re.compile("[\\x00\\x08\\x0b\\x0c\\x0e-\\x1f]")
_TITLE_SEG_RE = re.compile(r"\s+-\s+(19|20)\d{2}\s+-\s+")


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (t or "").lower())


def _md_candidates(root: Path) -> list[Path]:
    out = []
    for sub in ("all_md", "mineru_results"):
        d = root / sub
        if d.is_dir():
            out.extend(p for p in d.rglob("*.md") if p.stat().st_size > 3000)
    out.extend(p for p in root.glob("*.md") if p.stat().st_size > 3000)
    return out


def _match_key_from_name(name: str) -> str:
    """文件名 → 规范化匹配键：优先取 ' - YYYY - ' 之后的标题段。"""
    stem = name[:-3] if name.endswith(".md") else name
    m = _TITLE_SEG_RE.split(stem)
    if len(m) >= 3 and m[2]:
        stem = m[2]
    return _norm_title(stem)


def parse_paper_md(md_path: Path) -> list[dict]:
    """论文 MD：按 ## 标题分段 + 窗口合并；无标题回退滑窗。"""
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    text = _NUL_RE.sub(" ", text)
    lang = "zh" if _cjk_ratio(text[:6000]) > 0.15 else "en"
    lines = text.splitlines()

    sections, cur_title, cur_buf = [], "FRONT", []
    for line in lines:
        m = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if m:
            if cur_buf:
                sections.append((cur_title, "\n".join(cur_buf)))
            cur_title, cur_buf = m.group(1).strip(), []
        else:
            cur_buf.append(line)
    if cur_buf:
        sections.append((cur_title, "\n".join(cur_buf)))

    out = []
    for title, body in sections:
        for piece in _split_section(title, body):
            out.append({"section_path": title[:300], "content": piece, "lang": lang})
    return out


def import_paper_md(root: Path = DEFAULT_ROOT, limit: int | None = None) -> dict:
    # 索引1：pdf_path 文件名规范形 → work_id；索引2：标题规范形 → work_id
    by_pdfname, by_title = {}, {}
    for r in db.query("SELECT work_id, title, raw_data FROM mining.works"):
        pp = (r["raw_data"] or {}).get("pdf_path")
        if pp:
            by_pdfname[_norm_title(Path(pp).stem)] = r["work_id"]
        nt = _norm_title(r["title"])
        if nt and nt not in by_title:
            by_title[nt] = r["work_id"]

    mds = _md_candidates(root)
    print(f"发现 MD: {len(mds)}")
    stats = {"files": 0, "matched": 0, "unmatched": 0, "chunks": 0, "failed": 0}
    seen_works: set[int] = set()
    for md in mds:
        if limit and stats["files"] >= limit:
            break
        stats["files"] += 1

        # 匹配：整名 / "_" 后段（"作者-年_PDF名"格式）/ 标题段规范形
        stem = md.stem
        work_id = by_pdfname.get(_norm_title(stem))
        if not work_id:
            for seg in [stem] + stem.split("_"):
                nt = _norm_title(seg)
                work_id = by_pdfname.get(nt) or by_title.get(nt)
                if work_id:
                    break
        if not work_id:
            seg = _match_key_from_name(stem)
            work_id = by_title.get(seg) or by_pdfname.get(seg)
        if not work_id:
            stats["unmatched"] += 1
            continue
        if work_id in seen_works:
            continue  # 同一作品多解析版本：先到先得
        seen_works.add(work_id)

        sections = parse_paper_md(md)
        if len(sections) < 2:
            stats["failed"] += 1
            continue
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM mining.work_chunks WHERE work_id=%s", (work_id,))
            for idx, sec in enumerate(sections):
                cur.execute(
                    """
                    INSERT INTO mining.work_chunks
                        (work_id, lang, chunk_index, section_path, content, char_count, md_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (work_id, sec["lang"], idx, sec["section_path"],
                     sec["content"], len(sec["content"]), str(md)),
                )
        stats["chunks"] += len(sections)
        stats["matched"] += 1
        if stats["matched"] % 100 == 0:
            print(f"  {stats['matched']} matched, +{stats['chunks']} chunks")
    return stats


if __name__ == "__main__":
    root = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else DEFAULT_ROOT
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    print(import_paper_md(root=root, limit=lim))
