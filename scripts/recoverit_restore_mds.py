r"""恢复区带路径 syn\\ 树的 md 归位：完好校验 → E:\\syn 对应原路径（不覆盖）。"""
import shutil
import sys
from pathlib import Path

REC = Path(r"H:\Recoverit 2026-10-04 at 10.16.26\Local Disk (E)\syn")
SYN = Path(r"E:\syn")
STAGE = SYN / "_恢复损坏待修"


def md_ok(p: Path) -> bool:
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:400]
    except Exception:
        return False
    if not head:
        return False
    printable = sum(1 for c in head if c.isprintable() or c in "\n\r\t") / max(len(head), 1)
    if printable < 0.85:
        return False
    # 全零/短周期填充也算坏
    raw = p.read_bytes()[:128]
    for w in (1, 2, 4, 8):
        if len(raw) >= w * 8 and raw[:w] * (len(raw) // w) == raw[: len(raw) // w * w]:
            return False
    return True


def main() -> int:
    mds = sorted(REC.rglob("*.md"))
    print(f"恢复区 syn 树 md 共 {len(mds)}")
    ok = placed = 0
    targets = {}
    for p in mds:
        rel = p.relative_to(REC)
        good = md_ok(p)
        if good:
            ok += 1
            dst = SYN / rel
        else:
            dst = STAGE / "md损坏" / rel
        if dst.exists() and dst.stat().st_size == p.stat().st_size:
            continue
        if dst.exists():
            continue  # 不覆盖已有（保住唯一可用版本）
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        placed += 1
        targets.setdefault(str(dst.parent), []).append(dst.name)
    print(f"完好 {ok}/{len(mds)}，本次归位 {placed}")
    for d, names in sorted(targets.items()):
        print(f"  {d.replace(str(SYN), 'E:/syn')}: {len(names)}")
        for n in names[:3]:
            print(f"     {n[:66]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
