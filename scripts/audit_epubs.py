r"""EPUB 成果比对：E:\syn 全部 epub → H 盘成果区是否有同名副本。
输出 H 盘缺失清单（按目录分组），并可选 --copy 复制到 H 对应书籍目录。
"""
import shutil
import sys
from pathlib import Path

E_ROOT = Path(r"E:\syn")
H_AREAS = [
    Path(r"H:\00\mining_library"),
    Path(r"H:\Protected_EPUBs_v3"),
    Path(r"H:\00\Z-Library"),
]

h_names: dict[str, Path] = {}
for area in H_AREAS:
    for p in area.rglob("*.epub"):
        h_names.setdefault(p.name.lower(), p)

missing: dict[Path, list[Path]] = {}
n_e = n_have = 0
for p in E_ROOT.rglob("*.epub"):
    n_e += 1
    if p.name.lower() in h_names:
        n_have += 1
    else:
        missing.setdefault(p.parent, []).append(p)

print(f"E 盘 epub 共 {n_e}，H 盘已有同名 {n_have}，H 盘缺失 {sum(len(v) for v in missing.values())}\n")
for d, eps in sorted(missing.items()):
    print(f"-- {str(d).replace(str(E_ROOT), 'E:/syn')}")
    for e in eps:
        print(f"   {e.name}  ({e.stat().st_size // 1024} KB)")

if "--copy" in sys.argv:
    print("\n== 复制成果/阶段成果到 H 盘（过程件留在 E）==")
    CHAPTER_MAP = {  # Translatebook 分章翻译 → 书名
        "新建文件夹": "SME Surface Mining Handbook 中文分章",
        "新建文件夹 (2)": "Open Pit Mine Planning and Design 中文分章",
        "新建文件夹 (3)": "Economic Evaluation 中文分章",
        "新建文件夹 (4)": "Guidelines for Open Pit Slope Design 中文分章",
    }
    SKIP_DIRS = ("uploads", "mining_epub_work", "Calibre 书库")  # 过程件/Calibre 管理
    copied = skipped = 0
    for d, eps in sorted(missing.items()):
        rel = str(d).replace(str(E_ROOT), "")
        if any(s in rel for s in SKIP_DIRS) or d == E_ROOT:
            skipped += len(eps)
            continue
        if "Translatebook" in rel and d.name in CHAPTER_MAP:
            target_dir = (Path(r"H:\00\mining_library\books\_translate_chapters")
                          / CHAPTER_MAP[d.name])
        elif "Translatebook" in rel or "mining_epub_work" in rel:
            # Translatebook_Data 整书级成果 → 对应 H 书籍目录（按是否中文粗分）
            target_dir = Path(r"H:\00\mining_library\books\_recovered_epubs")
        else:
            target_dir = Path(r"H:\00\mining_library\books") / d.name
            if not target_dir.exists():
                target_dir = Path(r"H:\00\mining_library\books\_recovered_epubs") / d.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for e in eps:
            dst = target_dir / e.name
            if not dst.exists():
                shutil.copy2(e, dst)
                copied += 1
    print(f"复制 {copied} 个到 H 盘；过程件留 E {skipped} 个")
