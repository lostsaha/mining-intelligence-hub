r"""F:\\新建文件夹 时间戳 epub → 解析内部标题恢复书名（原地重命名）。
同名冲突加时间戳后缀；解析失败的保留原名。--dry 只列清单。
"""
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET

D = Path(r"F:\新建文件夹")


def epub_title(p: Path) -> str:
    try:
        with zipfile.ZipFile(p) as z:
            c = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            opf = re.search(r'full-path="([^"]+)"', c).group(1)
            root = ET.fromstring(re.sub(r'xmlns="[^"]+"', "", z.read(opf).decode("utf-8", "ignore"), count=1))
            for el in root.iter():
                if el.tag.split("}")[-1] == "title":
                    return (el.text or "").strip()
    except Exception:
        pass
    return ""


def main() -> int:
    dry = "--dry" in sys.argv
    eps = sorted(D.glob("*.epub"))
    print(f"共 {len(eps)} 个")
    rows = []
    used: set[str] = set()
    renamed = failed = 0
    for p in eps:
        ts = p.stem
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000)
        except ValueError:
            dt = None
        title = epub_title(p)
        if not title:
            failed += 1
            rows.append((dt, p.name, "[无法解析]", p))
            continue
        safe = re.sub(r'[\\/:*?"<>|]', "", title).strip()[:80] or p.stem
        final = safe
        if final in used or (D / f"{final}.epub").exists():
            final = f"{safe}_{ts[-6:]}"
        used.add(final)
        rows.append((dt, p.name, final, p))
    for dt, old, new, p in sorted(rows, key=lambda r: (r[0] or datetime.min)):
        mark = "=" if old == new + ".epub" else "->"
        print(f"{dt:%m-%d %H:%M if dt else ''} | {old[:22]:22s} {mark} {new[:60]}")
    if not dry:
        for dt, old, new, p in rows:
            if new == "[无法解析]":
                continue
            dst = D / f"{new}.epub"
            if not dst.exists():
                p.rename(dst)
                renamed += 1
    print(f"\n{'[dry] ' if dry else ''}重命名 {renamed if not dry else len(rows) - failed}，解析失败 {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
