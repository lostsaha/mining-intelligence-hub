r"""最新版鉴定：每本书的 Koodo 各代 + H 盘现有版本，按时间排出真正的最新版。

- Koodo 文件名为毫秒时间戳（导入时刻），最可靠
- H 盘文件用 mtime（保留原始创建时间）
- 输出每本书的最新版及其所在位置；--copy 把 H 盘缺失的最新版补进书目录
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET
import zipfile

BOOK = Path(r"C:\Users\hahn\AppData\Roaming\koodo-reader\uploads\data\book")
BOOKS_H = Path(r"H:\00\mining_library\books")


def epub_title(p: Path) -> str:
    try:
        with zipfile.ZipFile(p) as z:
            container = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
            opf = z.read(opf_path).decode("utf-8", "ignore")
            root = ET.fromstring(re.sub(r'xmlns="[^"]+"', "", opf, count=1))
            for el in root.iter():
                if el.tag.split("}")[-1] == "title":
                    return (el.text or "").strip()
    except Exception:
        pass
    return ""


def norm(t: str) -> str:
    t = re.sub(r"[（(].*?[)）]", "", t)
    t = re.sub(r"[ \-—_·：:,，。.]", "", t.lower())
    return t[:24]


def main() -> int:
    # Koodo 各代
    groups: dict[str, list[tuple[float, Path, str]]] = {}
    for p in BOOK.glob("*.epub"):
        m = re.match(r"(\d{13})\.epub", p.name)
        ts = int(m.group(1)) / 1000 if m else p.stat().st_mtime
        title = epub_title(p)
        groups.setdefault(norm(title), []).append((ts, p, title))

    print("== 多版本书的版本谱系（Koodo 各代 + H 盘文件）==")
    report = []
    for key, gens in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(gens) < 2:
            continue
        gens.sort(reverse=True)
        title = gens[0][2]
        latest_ts, latest_p, _ = gens[0]
        oldest_ts = gens[-1][0]
        gens_span = f"{datetime.fromtimestamp(oldest_ts):%m-%d}~{datetime.fromtimestamp(latest_ts):%m-%d}"
        # H 盘同书文件
        h_files = []
        h_dir = None
        for d in BOOKS_H.iterdir():
            if d.is_dir() and (norm(d.name)[:16] in key or key[:16] in norm(d.name)):
                h_dir = d
                break
        if h_dir:
            for f in h_dir.glob("*.epub"):
                h_files.append((f.stat().st_mtime, f))
        h_latest = max(h_files, key=lambda x: x[0]) if h_files else None
        latest_src = "Koodo"
        # 若 H 盘某文件比 Koodo 最新还新 → H 为准
        if h_latest and h_latest[0] > latest_ts:
            latest_ts, latest_p = h_latest
            latest_src = "H盘"
        latest_in_h = h_dir is not None and latest_p.resolve().parent == h_dir.resolve()
        report.append((title, gens_span, len(gens), latest_ts, latest_p, latest_src, latest_in_h, h_dir))

    for title, span, n, lts, lp, src, in_h, h_dir in sorted(report, key=lambda r: r[3], reverse=True):
        mark = "OK " if in_h else "补!"
        print(f"[{mark}] {datetime.fromtimestamp(lts):%m-%d %H:%M} | {n:3d}代({span}) | {src:4s} | {title[:40]:40s} | {lp.name[:44]}")

    if "--copy" in sys.argv:
        print("\n== 补拷最新版到 H 盘书目录 ==")
        for title, span, n, lts, lp, src, in_h, h_dir in report:
            if in_h or h_dir is None:
                continue
            safe = re.sub(r'[\\/:*?"<>|]', "", title)[:70]
            dst = h_dir / f"{safe}_最新版{datetime.fromtimestamp(lts):%m%d}.epub"
            if not dst.exists():
                shutil.copy2(lp, dst)
                print(f"   -> {dst.name[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
