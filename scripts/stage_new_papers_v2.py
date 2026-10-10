r"""Zotero 新增论文整理（v2）：链接式附件（linkMode=1/2）+ 存储式附件全量对账。
链接文件从绝对路径复制；输出 E:\syn\papers_pending_mineru_新批次_20261004\
"""
import re
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from app.documents.find_unparsed import (  # noqa: E402
    ALLMD_DIR, MINERU_DIR, _title_after_year, _norm,
)

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
ZOTERO_STORAGE = Path(r"E:\Zotero\storage")
OUT = Path(r"E:\syn\papers_pending_mineru_新批次_20261004")


def parsed_keys() -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    keys_list: list[str] = []
    if MINERU_DIR.is_dir():
        for f in MINERU_DIR.rglob("*.md"):
            for cand in (f.parent.name, f.stem):
                k = _title_after_year(cand)
                if len(k) >= 12:
                    keys.add(k)
                    keys_list.append(k)
    if ALLMD_DIR.is_dir():
        for f in ALLMD_DIR.glob("*.md"):
            for cand in (f.stem.split("_", 1)[0], f.stem.split("_", 1)[-1]):
                k = _title_after_year(cand)
                if len(k) >= 12:
                    keys.add(k)
                    keys_list.append(k)
    return keys, keys_list


def all_pdfs() -> list[dict]:
    """存储式 + 链接式附件的 PDF（父标题 join 内联字段过滤，防行膨胀）。"""
    conn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=10)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ai.key, a.linkMode, a.path,
               COALESCE(pt.value, '') AS title, substr(ai.dateAdded, 1, 10) AS d
        FROM itemAttachments a
        JOIN items ai ON ai.itemID = a.itemID
        LEFT JOIN items pi ON pi.itemID = a.parentItemID
        LEFT JOIN itemData pd ON pd.itemID = a.parentItemID
             AND pd.itemID IS NOT NULL
             AND pd.valueID IN (SELECT valueID FROM itemData WHERE fieldID =
                (SELECT fieldID FROM fields WHERE fieldName = 'title'))
        LEFT JOIN itemDataValues pt ON pt.valueID = pd.valueID
        WHERE a.contentType = 'application/pdf'
          AND a.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND a.parentItemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    out = []
    for key, lm, path, title, d in cur.fetchall():
        if lm == 0:
            fname = (path or "").replace("storage:", "")
            full = ZOTERO_STORAGE / key / fname
        elif lm == 2:
            full = Path((path or "").replace("file://", ""))
        else:
            continue  # linkMode=1 是 URL，无本地文件
        if title and full.exists():
            out.append({"pdf": full, "title": title, "date": d, "lm": lm})
    conn.close()
    return out


def main() -> int:
    copy = "--copy" in sys.argv
    keys, keys_list = parsed_keys()
    pdfs = all_pdfs()
    staged = set()
    for d in (Path(r"E:\syn\papers_pending_mineru"),
              Path(r"H:\00\mining_library\papers_pending_mineru"),
              OUT):
        if d.is_dir():
            staged |= {p.name for p in d.glob("*.pdf")}
    print(f"全量 PDF 附件（含链接式）: {len(pdfs)} | 旧批次已暂存 {len(staged)}")

    unparsed, overlapped = [], 0
    for p in pdfs:
        k = _title_after_year(p["pdf"].stem)
        if k in keys or len(k) < 12:
            continue
        if any((k in pk or pk in k) and min(len(k), len(pk)) >= 20 for pk in keys_list):
            continue
        if p["pdf"].name in staged:
            overlapped += 1
            continue
        unparsed.append(p)
    print(f"未解析 {len(unparsed) + overlapped}，其中旧批次已暂存 {overlapped}，真正新增 {len(unparsed)}")

    if copy and unparsed:
        OUT.mkdir(parents=True, exist_ok=True)  # 不清空输出文件夹（增量并入）
        OUT.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        lines = []
        n = 0
        for p in sorted(unparsed, key=lambda x: x["date"]):
            dst = OUT / p["pdf"].name
            if dst.exists() and dst.stat().st_size == p["pdf"].stat().st_size:
                continue
            if dst.exists():
                dst = OUT / f"{p['date']}_{p['pdf'].name}"
            shutil.copy2(p["pdf"], dst)
            seen.add(p["pdf"].name)
            n += 1
            lines.append(f"- {p['date']} | {p['title'][:88]}（{p['pdf'].name}）")
        (OUT / "_清单.md").write_text(
            f"# 新增论文待解析清单（{n} 篇）\n\n"
            "来源：Zotero 链接式附件（E:\\references_papers）+ 存储式新增。\n"
            "MinerU 解析后 md 放回 H:\\00\\zotero\\mineru_results\\，然后\n"
            "`python -m app.documents.import_paper_md` 入库。\n\n" + "\n".join(lines),
            encoding="utf-8",
        )
        print(f"已复制 {n} 个 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
