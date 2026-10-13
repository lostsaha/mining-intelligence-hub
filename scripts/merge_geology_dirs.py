r"""地质双目录并轨：鍦拌川 → 地质。同名同大小跳过；异大小留 mtime 新；仅B有移入。"""
import shutil
import sys
from pathlib import Path

A = Path(r"E:\syn\地质")
B = Path(r"E:\syn\鍦拌川")


def main() -> int:
    same = newer_a = newer_b = only_b = moved = replaced = 0
    if not B.exists():
        print("鍦拌川 不存在")
        return 0
    files = [f for f in B.rglob("*") if f.is_file()]
    for fb in files:
        fa = A / fb.relative_to(B)
        if fa.exists():
            if fa.stat().st_size == fb.stat().st_size:
                same += 1
            elif fa.stat().st_mtime >= fb.stat().st_mtime:
                newer_a += 1
            else:
                # B 较新：备份 A 旧版后替换
                bak = A.parent / "地质_并轨备份" / fb.relative_to(B)
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fa, bak)
                shutil.copy2(fb, fa)
                replaced += 1
        else:
            fa.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(fb), str(fa))
            moved += 1
    print(f"比对 {len(files)} 文件：相同 {same} | A较新 {newer_a} | B较新替换 {replaced}（旧版备份到 地质_并轨备份\\）| 仅B移入 {moved}")
    # 清空 B 的空目录结构
    for d in sorted((p for p in B.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            d.rmdir()
        except OSError:
            pass
    try:
        B.rmdir()
        print("鍦拌川 目录已删除（并轨完成）")
    except OSError:
        left = sum(1 for _ in B.rglob("*"))
        print(f"鍦拌川 仍有 {left} 项残留（含非空目录），人工查看")
    return 0


if __name__ == "__main__":
    sys.exit(main())
