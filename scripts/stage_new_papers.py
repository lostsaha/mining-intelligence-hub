r"""整理 Zotero 新增论文（未解析且未暂存）→ E:\syn\papers_pending_mineru_新批次_20261004\

- 解析键适配 mineru_results 新结构（Book/CN/En/学位论文/会议论文集 递归 md）
- 排除已暂存（E/H 两处 papers_pending_mineru 按文件名）
- 用法：python stage_new_papers.py [--copy]
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from app.documents.find_unparsed import (  # noqa: E402
    ALLMD_DIR, MINERU_DIR, _norm, _title_after_year, zotero_pdfs,
)

STAGED_DIRS = [
    Path(r"E:\syn\papers_pending_mineru"),
    Path(r"H:\00\mining_library\papers_pending_mineru"),
    Path(r"E:\syn\待解析_mineru"),
]
OUT = Path(r"E:\syn\papers_pending_mineru_新批次_20261004")


def parsed_keys_v2() -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    keys_list: list[str] = []
    # mineru_results：递归所有 md（新分类结构），键取 父目录名 与 文件名 两种
    if MINERU_DIR.is_dir():
        for f in MINERU_DIR.rglob("*.md"):
            for cand in (f.parent.name, f.stem):
                k = _title_after_year(cand)
                if len(k) >= 12:
                    keys.add(k)
                    keys_list.append(k)
    # all_md：文件名两段都取
    if ALLMD_DIR.is_dir():
        for f in ALLMD_DIR.glob("*.md"):
            for cand in (f.stem.split("_", 1)[0], f.stem.split("_", 1)[-1]):
                k = _title_after_year(cand)
                if len(k) >= 12:
                    keys.add(k)
                    keys_list.append(k)
    return keys, keys_list


def staged_names() -> set[str]:
    names: set[str] = set()
    for d in STAGED_DIRS:
        if d.is_dir():
            names |= {p.name for p in d.glob("*.pdf")} | {p.name for p in d.glob("*.PDF")}
    return names


def main() -> int:
    copy = "--copy" in sys.argv
    keys, keys_list = parsed_keys_v2()
    pdfs = zotero_pdfs()
    staged = staged_names()
    print(f"已解析键 {len(keys)} | Zotero PDF {len(pdfs)} | 已暂存 {len(staged)}")

    unparsed, new = [], 0
    for p in pdfs:
        k = _title_after_year(p["pdf"].stem)
        if k in keys or len(k) < 12:
            continue
        if any((k in pk or pk in k) and min(len(k), len(pk)) >= 20 for pk in keys_list):
            continue
        unparsed.append(p)
        if p["pdf"].name not in staged:
            new += 1
            if copy:
                OUT.mkdir(parents=True, exist_ok=True)
                dst = OUT / p["pdf"].name
                if not dst.exists():
                    shutil.copy2(p["pdf"], dst)
    print(f"未解析共 {len(unparsed)}，其中未暂存新论文 {new}")
    if copy and new:
        lines = [f"- {p['title'][:90]}（{p['pdf'].name}）" for p in unparsed
                 if p["pdf"].name not in staged]
        (OUT / "_清单.md").write_text(
            f"# 新增论文待解析清单（{len(lines)} 篇，2026-10-04）\n\n"
            "MinerU 解析后把输出 md 放回 H:\\00\\zotero\\mineru_results\\（按 En/CN 分类或顶层均可），\n"
            "然后运行 `python -m app.documents.import_paper_md` 入库。\n\n" + "\n".join(lines),
            encoding="utf-8",
        )
        print(f"已复制 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
