r"""合并 mineru任务汇总 两处解析 md 到正规 mineru_results（canonical 缺失的才拷，源不删）。
1013 批次按其子目录映射（book→Book / en→EN / 会议论文→会议论文集）；
汇总-mineru_results 顶层 md 按文件名 CJK 分 CN/EN。
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app.documents.find_unparsed import _title_after_year  # noqa: E402

CANON = Path(r"H:\00\zotero\mineru_results")
SOURCES = [
    (Path(r"H:\00\mineru任务汇总\mineru_results1013"), "sub"),   # 保留子目录映射
    (Path(r"H:\00\mineru任务汇总\mineru_results"), "top"),       # 顶层按语言
]
CJK = re.compile(r"[\u4e00-\u9fff]")


def main() -> int:
    # canonical 已有键 → 已有文件路径集合（避免按 key 重复拷贝）
    canon_keys: dict[str, Path] = {}
    canon_files = {f.name for f in CANON.rglob("*.md")}
    for f in CANON.rglob("*.md"):
        for c in (f.parent.name if len(f.parent.name) > 12 else f.stem, f.stem):
            k = _title_after_year(c)
            if len(k) >= 12 and k not in canon_keys:
                canon_keys[k] = f
    print(f"canonical 现有 md {len(canon_files)}，键 {len(canon_keys)}")

    copied = skipped = 0
    for src, mode in SOURCES:
        if not src.exists():
            print(f"[缺源] {src}")
            continue
        for f in sorted(src.rglob("*.md")):
            if f.name in canon_files:
                skipped += 1
                continue
            k = _title_after_year(f.parent.name if len(f.parent.name) > 12 else f.stem)
            if len(k) >= 12 and k in canon_keys:
                skipped += 1
                continue
            # 决定目标分类
            if mode == "sub":
                top = f.relative_to(src).parts[0].lower()
                cat = {"book": "Book", "en": "EN", "会议论文": "会议论文集",
                       "cn": "CN", "学位论文": "学位论文"}.get(top)
                if not cat:
                    cat = "CN" if CJK.search(f.name) else "EN"
            else:
                cat = "CN" if CJK.search(f.name) else "EN"
            dst_dir = CANON / cat
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f.name
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(f, dst)
            canon_files.add(f.name)
            if len(k) >= 12:
                canon_keys.setdefault(k, dst)
            copied += 1
    print(f"并入 canonical: 拷贝 {copied}，跳过（已存在/同键） {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
