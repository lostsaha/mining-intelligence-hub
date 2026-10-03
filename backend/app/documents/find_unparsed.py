"""对账：Zotero PDF 全文 vs 已解析 MD（mineru_results + all_md）。

输出：
- 未解析 PDF 复制到 E:\\syn\\待解析_mineru\\（复制不移动，Zotero storage 原样保留）
- E:\\syn\\待解析_mineru\\_清单.md —— 标题清单（可照此在 Zotero 建集合跑 magic 插件）
用法：python -m app.documents.find_unparsed [--copy]
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from pathlib import Path

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
ZOTERO_STORAGE = Path(r"E:\Zotero\storage")
MINERU_DIR = Path(r"H:\00\zotero\mineru_results")
ALLMD_DIR = Path(r"H:\00\zotero\all_md")
OUT_DIR = Path(r"E:\syn\待解析_mineru")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (t or "").lower())


def _title_after_year(name: str) -> str:
    """'Author 等 - 2015 - Title.pdf' 或 '2015 - Title' → 'Title' 规范形。"""
    m = re.search(r"(?:^|\s-\s)(19|20)\d{2}\s+-\s+(.+)$", name)
    if m:
        return _norm(m.group(2))
    return _norm(name)


def parsed_keys() -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    keys_list: list[str] = []
    # mineru_results：有顶层 .md 的目录
    for d in MINERU_DIR.iterdir() if MINERU_DIR.is_dir() else []:
        if not d.is_dir():
            continue
        if any(md.suffix == ".md" for md in d.iterdir()):
            k = _title_after_year(d.name)
            if len(k) >= 15:
                keys.add(k)
                keys_list.append(k)
    # all_md：文件名第二段（" - YYYY - " 之后）
    if ALLMD_DIR.is_dir():
        for f in ALLMD_DIR.glob("*.md"):
            k = _title_after_year(f.stem)
            if len(k) >= 15:
                keys.add(k)
                keys_list.append(k)
    return keys, keys_list


def zotero_pdfs() -> list[dict]:
    # 直连只读（Zotero 关闭时无锁）；busy_timeout 兜底并发
    conn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=10)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ai.key, a.path, COALESCE(pt.value, '') FROM itemAttachments a
        JOIN items ai ON ai.itemID = a.itemID
        JOIN items pi ON pi.itemID = a.parentItemID
        JOIN itemData pd ON pd.itemID = pi.itemID
        JOIN fields pf ON pf.fieldID = pd.fieldID AND pf.fieldName = 'title'
        JOIN itemDataValues pt ON pt.valueID = pd.valueID
        WHERE a.contentType = 'application/pdf' AND a.linkMode = 0
          AND a.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND a.parentItemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    out = []
    for key, path, parent_title in cur.fetchall():
        fname = (path or "").replace("storage:", "")
        full = ZOTERO_STORAGE / key / fname
        if full.exists():
            out.append({"key": key, "pdf": full, "title": parent_title or fname})
    conn.close()
    return out


def main(copy: bool = False) -> dict:
    keys, keys_list = parsed_keys()
    pdfs = zotero_pdfs()
    print(f"已解析键: {len(keys)} | Zotero PDF: {len(pdfs)}")

    unmatched, matched = [], 0
    for p in pdfs:
        k = _title_after_year(p["pdf"].stem)
        if k in keys or len(k) < 12:
            matched += 1
            continue
        # 包含匹配（键长度足够时）
        hit = any((k in pk or pk in k) and min(len(k), len(pk)) >= 20 for pk in keys_list)
        if hit:
            matched += 1
        else:
            unmatched.append(p)

    print(f"已解析: {matched} | 未解析: {len(unmatched)}")
    if copy and unmatched:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for p in unmatched:
            shutil.copy2(p["pdf"], OUT_DIR / p["pdf"].name)
        lines = [f"- {p['title'][:90]}（{p['pdf'].name}）" for p in unmatched]
        (OUT_DIR / "_清单.md").write_text(
            "# 未解析论文清单（Zotero PDF）\n\n"
            "以下 PDF 尚无 MinerU 解析结果。两种处理方式：\n"
            "1. 用 MinerU 解析本目录下 PDF；\n"
            "2. 在 Zotero 中按标题建集合，用 magic 插件解析。\n\n" + "\n".join(lines),
            encoding="utf-8",
        )
        print(f"已复制 {len(unmatched)} 个 PDF → {OUT_DIR}")
    return {"parsed": matched, "unparsed": len(unmatched)}


if __name__ == "__main__":
    main(copy="--copy" in sys.argv)
