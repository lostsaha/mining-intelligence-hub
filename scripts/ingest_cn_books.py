r"""E:\syn\书籍\CN 中文矿业专著入库（保留源文件，原地登记）。

结构：每书一目录（md + pdf + images），修复过的 EPUB 集中在 epub\。
- md 标题层级不可信 → EPUB 目录做骨架权威（import_books 同款骨架对齐）
- 每单元注册 document（title_zh）+ md 版本（骨架分段）+ epub 版本（待 import_epub_chunks 分段）
- epub\ 里没有对应目录的（如《采矿手册》第7卷）注册为 epub-only 文档
- 用法：python ingest_cn_books.py
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
sys.path.insert(0, r"E:\syn\矿业聚合平台\scripts")

from app import db  # noqa: E402
from app.documents.import_books import (  # noqa: E402
    _CLEAN_TAIL, _zh_toc_skeleton, epub_toc, parse_markdown,
)

ROOT = Path(r"E:\syn\书籍\CN")
EPUB_DIR = ROOT / "epub"
SKIP_PARTS = {"work", "epub", "__pycache__"}
CONTAINER_UNITS = {"采矿手册"}  # 只作容器（卷册在其子目录），本身不作为书籍
EPUB_SKIP = {"采矿手册第3卷1-267页"}  # 部分卷的重复修复版，入库会重复
_CN_NUM = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
           "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"v(\d+)", r"第\1卷", s)
    for cn, ar in _CN_NUM.items():
        s = s.replace(f"第{cn}", f"第{ar}")
    s = re.sub(r"[ \(\)（）\-—_·、，,。《》\[\]\"']+", "", s)
    return s.replace("merged", "").replace("zlibrary", "")


def match_name(unit: Path) -> str:
    """嵌套单元用 父目录名+目录名（上册→现代采矿手册上册；V1→采矿手册第1卷）。"""
    base = unit.name if unit.parent == ROOT else f"{unit.parent.name}{unit.name}"
    return norm(base)


def find_units() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_dir() or set(p.parts) & SKIP_PARTS or p.name in CONTAINER_UNITS:
            continue
        if any(p.glob("*.md")) or any(p.glob("*.pdf")):
            out.append(p)
    return out


def pick_md(unit: Path) -> Path | None:
    mds = [m for m in unit.glob("*.md")]
    return max(mds, key=lambda m: m.stat().st_size) if mds else None


def main() -> int:
    if "--wipe" in sys.argv:
        prefix = str(ROOT)
        like = prefix + "\u0001"  # 占位，实际用 left() 前缀比较
        db.execute(
            "DELETE FROM mining.document_chunks WHERE document_id IN "
            "(SELECT document_id FROM mining.documents WHERE left(source_dir,%s)=%s)",
            (len(prefix), prefix),
        )
        db.execute(
            "DELETE FROM mining.document_versions WHERE document_id IN "
            "(SELECT document_id FROM mining.documents WHERE left(source_dir,%s)=%s)",
            (len(prefix), prefix),
        )
        n = db.query_one(
            "SELECT COUNT(*) n FROM mining.documents WHERE left(source_dir,%s)=%s",
            (len(prefix), prefix),
        )["n"]
        db.execute(
            "DELETE FROM mining.documents WHERE left(source_dir,%s)=%s",
            (len(prefix), prefix),
        )
        print(f"已清除旧登记 {n} 条")

    units = find_units()
    epubs = [e for e in sorted(EPUB_DIR.glob("*.epub")) if norm(e.stem) not in EPUB_SKIP]
    print(f"书籍单元 {len(units)} 个，EPUB {len(epubs)} 个")

    # EPUB 匹配：先精确（归一化后相等），再模糊（每个 epub 只归一个单元）
    assign: dict[Path, Path] = {}  # unit -> epub
    used: set[Path] = set()
    for u in units:
        mn = match_name(u)
        exact = next((e for e in epubs if norm(e.stem) == mn), None)
        if exact:
            assign[u] = exact
            used.add(exact)
    pairs = []
    for u in units:
        if u in assign:
            continue
        mn = match_name(u)
        best, br = None, 0.0
        for e in epubs:
            if e in used:
                continue
            r = difflib.SequenceMatcher(None, mn, norm(e.stem)).ratio()
            if r > br:
                best, br = e, r
        if best and br >= 0.45:
            pairs.append((br, u, best))
    for br, u, e in sorted(pairs, reverse=True):
        if e not in used:
            assign[u] = e
            used.add(e)

    stats = {"docs": 0, "md_chunks": 0, "epub_only": 0, "failed": 0}
    for u in units:
        md = pick_md(u)
        pdfs = sorted(u.glob("*.pdf"))
        # 容器根的卷册 PDF 分配给对应卷（采矿手册(第N卷).pdf → 第N卷单元）
        if u.parent.name in CONTAINER_UNITS:
            m = re.search(r"第(\d+)卷|([Vv])(\d+)", u.name)
            vol = (m.group(1) or m.group(3)) if m else None
            if vol:
                pdfs += [p for p in (ROOT / u.parent.name).glob("*.pdf")
                         if re.search(f"第{vol}卷", p.stem)]
        epub = assign.get(u)
        if not md and not epub:
            print(f"[skip] {u.name[:52]}（无 md/epub）")
            continue
        title = re.sub(_CLEAN_TAIL, " ", md.stem if md else epub.stem).strip()
        title = re.sub(r"_merged$", "", title).strip()
        skeleton = None
        if epub:
            t = epub_toc(epub)
            skeleton = _zh_toc_skeleton(t) if t else None

        row = db.query_one(
            """
            INSERT INTO mining.documents (title_en, title_zh, doc_type, source_dir)
            VALUES (%s, %s, 'book', %s)
            ON CONFLICT (source_dir) DO UPDATE SET title_zh = EXCLUDED.title_zh
            RETURNING document_id
            """,
            (title[:300], title[:300], str(u)),
        )
        doc_id = row["document_id"]
        if skeleton:
            db.execute(
                "UPDATE mining.documents SET raw_toc=%s WHERE document_id=%s",
                (json.dumps(skeleton, ensure_ascii=False), doc_id),
            )
        stats["docs"] += 1

        if md:
            vrow = db.query_one(
                """
                INSERT INTO mining.document_versions
                    (document_id, lang, format, file_path, file_size, parse_status)
                VALUES (%s, 'zh', 'md', %s, %s, 'pending')
                ON CONFLICT (file_path) DO UPDATE SET parse_status='pending'
                RETURNING version_id
                """,
                (doc_id, str(md), md.stat().st_size),
            )
            sections = parse_markdown(md, skeleton)
            if len(sections) < 5:
                db.execute("UPDATE mining.document_versions SET parse_status='failed' WHERE version_id=%s",
                           (vrow["version_id"],))
                stats["failed"] += 1
                print(f"[warn] {title[:40]} md 分段过少({len(sections)})")
            else:
                db.execute("DELETE FROM mining.document_chunks WHERE version_id=%s", (vrow["version_id"],))
                with db.get_conn() as conn, conn.cursor() as cur:
                    for idx, sec in enumerate(sections):
                        cur.execute(
                            """INSERT INTO mining.document_chunks
                               (document_id, version_id, lang, chunk_index, section_path, content, char_count)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (doc_id, vrow["version_id"], sec["lang"], idx,
                             sec["section_path"][:300], sec["content"], len(sec["content"])),
                        )
                stats["md_chunks"] += len(sections)
                db.execute("UPDATE mining.document_versions SET parse_status='parsed' WHERE version_id=%s",
                           (vrow["version_id"],))

        if epub:
            db.query_one(
                """
                INSERT INTO mining.document_versions
                    (document_id, lang, format, file_path, file_size, parse_status)
                VALUES (%s, 'zh', 'epub', %s, %s, 'pending')
                ON CONFLICT (file_path) DO UPDATE SET parse_status='pending'
                RETURNING version_id
                """,
                (doc_id, str(epub), epub.stat().st_size),
            )
        for pdf in pdfs:
            db.query_one(
                """
                INSERT INTO mining.document_versions
                    (document_id, lang, format, file_path, file_size, parse_status)
                VALUES (%s, 'zh', 'pdf', %s, %s, 'skipped')
                ON CONFLICT (file_path) DO UPDATE SET parse_status='skipped'
                RETURNING version_id
                """,
                (doc_id, str(pdf), pdf.stat().st_size),
            )
        print(f"[cn] {title[:44]:44s} md={'Y' if md else '-'} epub={epub.stem[:18] if epub else '-'} "
              f"骨架={'Y' if skeleton else '-'}")

    # 无单元对应的 EPUB → epub-only 文档（source_dir 用文件路径保证唯一）
    for e in epubs:
        if e in used:
            continue
        row = db.query_one(
            """
            INSERT INTO mining.documents (title_en, title_zh, doc_type, source_dir)
            VALUES (%s, %s, 'book', %s)
            ON CONFLICT (source_dir) DO UPDATE SET title_zh = EXCLUDED.title_zh
            RETURNING document_id
            """,
            (e.stem[:300], e.stem[:300], str(e)),
        )
        db.query_one(
            """
            INSERT INTO mining.document_versions
                (document_id, lang, format, file_path, file_size, parse_status)
            VALUES (%s, 'zh', 'epub', %s, %s, 'pending')
            ON CONFLICT (file_path) DO UPDATE SET parse_status='pending'
            RETURNING version_id
            """,
            (row["document_id"], str(e), e.stat().st_size),
        )
        stats["docs"] += 1
        stats["epub_only"] += 1
        print(f"[cn-epub-only] {e.stem[:52]}")

    print(f"\n登记完成：{stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
