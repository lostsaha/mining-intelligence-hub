r"""全盘扫描 MinerU 解析输出，找出未归入 mineru_results/all_md 的漏网论文。

签名：目录内同时有 .md 和 images\ 子目录（MinerU 标准输出），或 *_origin.md。
比对已解析键（递归 mineru_results + all_md），列出键未命中的 md。
范围：E 盘（3 层）、F 盘（3 层）、H:\00（4 层）、Downloads（3 层）。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app.documents.find_unparsed import _title_after_year  # noqa: E402

MINERU = Path(r"H:\00\zotero\mineru_results")
ALLMD = Path(r"H:\00\zotero\all_md")
SKIP_PARTS = {"矿业聚合平台", ".venv", "node_modules", "__pycache__", "storage",
              "books", "标准-露天矿山", "$RECYCLE.BIN", "System Volume Information",
              "待解析_mineru", "papers_pending_mineru", "书籍"}
AREAS = [
    (Path(r"E:\\"), 3),
    (Path(r"F:\\"), 3),
    (Path(r"H:\00"), 4),
    (Path(r"C:\Users\hahn\Downloads"), 3),
]


def canonical_keys() -> set[str]:
    keys = set()
    for f in MINERU.rglob("*.md"):
        for cand in (f.parent.name, f.stem):
            keys.add(_title_after_year(cand))
    for f in ALLMD.glob("*.md"):
        for cand in (f.stem.split("_", 1)[0], f.stem.split("_", 1)[-1]):
            keys.add(_title_after_year(cand))
    return keys


def main() -> int:
    keys = canonical_keys()
    print(f"已解析键 {len(keys)}\n== 扫描 MinerU 输出签名 ==")
    found: dict[Path, list[Path]] = {}
    for area, depth in AREAS:
        if not area.exists():
            continue
        for md in area.rglob("*.md"):
            if md.is_symlink() or len(md.relative_to(area).parts) > depth:
                continue
            if any(part in SKIP_PARTS for part in md.parts):
                continue
            d = md.parent
            if d == MINERU or MINERU in d.parents or d == ALLMD or ALLMD in d.parents:
                continue
            has_images = (d / "images").is_dir()
            is_origin = md.stem.endswith("_origin")
            if not (has_images or is_origin):
                continue
            k = _title_after_year(md.stem if len(md.stem) > 12 else d.name)
            if len(k) >= 12 and k in keys:
                continue
            found.setdefault(d, []).append(md)

    total_new = sum(len(v) for v in found.values())
    print(f"疑似未归入的输出目录 {len(found)} 个，md {total_new} 个\n")
    for d, mds in sorted(found.items(), key=lambda kv: -len(kv[1]))[:25]:
        print(f"[{len(mds):3d}] {str(d)[:90]}")
        for m in mds[:2]:
            print(f"      {m.name[:76]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
