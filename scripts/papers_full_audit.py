r"""论文全库总对账：
1) 收集全部 PDF（Zotero 2304 + 两批暂存 + 零散）
2) 收集全部已解析 md 键（H 盘 mineru_results 递归 / all_md / E 盘 mineru_results 递归）
3) PG works 标题键（已入库语料）
4) 输出分类账：已解析未入库 / 未解析 / 已入库 / 各论文集清单
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import db  # noqa: E402
from app.documents.find_unparsed import _norm, _title_after_year, zotero_pdfs  # noqa: E402

PDF_SOURCES = [
    Path(r"E:\syn\papers_pending_mineru"),
    Path(r"E:\syn\papers_pending_mineru_新批次_20261004"),
]
MD_AREAS = [
    Path(r"H:\00\zotero\mineru_results"),
    Path(r"H:\00\zotero\all_md"),
    Path(r"E:\syn\mineru_results"),
]


def all_md_files() -> list[Path]:
    mds = []
    for a in MD_AREAS:
        if a.exists():
            mds.extend(a.rglob("*.md"))
    return mds


def main() -> int:
    # 1) PDF 池（Zotero + 暂存批次，按文件名去重）
    pdfs: dict[str, dict] = {}
    for p in zotero_pdfs():
        pdfs.setdefault(p["pdf"].name, {"path": p["pdf"], "title": p["title"], "src": "zotero"})
    for d in PDF_SOURCES:
        if not d.exists():
            continue
        for f in d.rglob("*.pdf"):
            if f.name not in pdfs:
                pdfs[f.name] = {"path": f, "title": f.stem, "src": f"staged:{d.name[-8:]}"}
    print(f"PDF 池（去重后）: {len(pdfs)}")

    # 2) 已解析键（三处 md 源）
    parsed_keys, parsed_list = set(), []
    for m in all_md_files():
        for cand in (m.parent.name, m.stem, m.stem.split("_", 1)[-1] if "_" in m.stem else m.stem):
            k = _title_after_year(cand)
            if len(k) >= 12:
                parsed_keys.add(k)
                parsed_list.append(k)
    # 3) PG works 标题键
    rows = db.query("SELECT title FROM mining.works WHERE title IS NOT NULL")
    pg_keys = {_norm(r["title"])[:60] for r in rows}
    print(f"已解析键 {len(parsed_keys)} | PG works 标题键 {len(pg_keys)}")

    cats = {"parsed_not_in_pg": [], "parsed_in_pg": [], "unparsed": []}
    for name, info in pdfs.items():
        k = _title_after_year(Path(name).stem)
        if len(k) < 12:
            k = _norm(info["title"])[:40]
        is_parsed = any((k in pk or pk in k) and min(len(k), len(pk)) >= 20 for pk in parsed_list) if len(k) >= 12 else False
        nk = _norm(info["title"])[:60]
        in_pg = nk in pg_keys or (len(nk) >= 20 and any(nk in g or g in nk for g in pg_keys))
        if is_parsed:
            (cats["parsed_in_pg"] if in_pg else cats["parsed_not_in_pg"]).append(info)
        else:
            (cats["parsed_not_in_pg"] if in_pg else cats["unparsed"]).append(info)

    print(f"\n== 分类账 ==")
    print(f"已解析+已入库   : {len(cats['parsed_in_pg'])}")
    print(f"已解析+未入库md : {len(cats['parsed_not_in_pg'])}   ← import_paper_md 增量队列")
    print(f"未解析          : {len(cats['unparsed'])}   ← MinerU 队列（含两批暂存+新论文）")
    for c in ("parsed_not_in_pg", "unparsed"):
        print(f"\n-- {c} 样例:")
        for info in cats[c][:6]:
            print(f"   {info['src'][:12]:12s} {info['title'][:64]}")

    # 4) 未解析按来源分布（给 MinerU 跑批规模）
    from collections import Counter
    src = Counter(i["src"] for i in cats["unparsed"])
    print("\n未解析按来源:", dict(src))
    return 0


if __name__ == "__main__":
    sys.exit(main())
