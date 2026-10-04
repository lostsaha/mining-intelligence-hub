r"""Koodo Reader 书库盘点：解析每本 EPUB 的标题/作者/语言，找出中文成果。
与 E:\syn + H 盘已归档 EPUB 文件名比对，标出"新发现"（未归档）的书。
--copy：新发现的中文书复制到 H:\00\mining_library\books\_koodo_recovered\<标题>.epub
"""
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET

BOOK = Path(r"C:\Users\hahn\AppData\Roaming\koodo-reader\uploads\data\book")
H_NEW = Path(r"H:\00\mining_library\books\_koodo_recovered")
SCAN_AREAS = [
    Path(r"E:\syn"),
    Path(r"H:\00\mining_library"),
    Path(r"H:\00\Z-Library"),
    Path(r"H:\Zlibrary"),
    Path(r"H:\Protected_EPUBs_v3"),
]

CJK = re.compile(r"[\u4e00-\u9fff]{2,}")


def epub_meta(p: Path) -> tuple[str, str, str]:
    try:
        with zipfile.ZipFile(p) as z:
            container = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
            opf = z.read(opf_path).decode("utf-8", "ignore")
            root = ET.fromstring(re.sub(r'xmlns="[^"]+"', "", opf, count=1))
            ns = "http://www.idpf.org/2007/opf"  # noqa: F841
            def get(tag):
                el = root.find(f".//{tag.split('-')[0]}:{tag.split('-')[1]}".replace("dc:", "dc:"))
                return None
            title = creator = lang = ""
            for el in root.iter():
                t = el.tag.split("}")[-1]
                if t == "title" and not title:
                    title = (el.text or "").strip()
                elif t == "creator" and not creator:
                    creator = (el.text or "").strip()
                elif t == "language" and not lang:
                    lang = (el.text or "").strip()
            return title, creator, lang
    except Exception:
        return "?", "?", "?"


def main() -> int:
    known: set[str] = set()
    for area in SCAN_AREAS:
        if area.exists():
            for p in area.rglob("*.epub"):
                known.add(p.name)
    rows = []
    for p in sorted(BOOK.glob("*.epub")):
        title, creator, lang = epub_meta(p)
        mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d")
        rows.append((p, title, creator, lang, mt, p.stat().st_size))
    zh = [r for r in rows if CJK.search(r[1] or "") or (r[3] or "").startswith("zh")]
    print(f"Koodo 库 {len(rows)} 本，其中中文书 {len(zh)} 本\n")

    new = []
    for p, title, creator, lang, mt, size in sorted(zh, key=lambda r: r[4]):
        cjk_runs = CJK.findall(title or "")
        archived = False
        if cjk_runs:
            core = max(cjk_runs, key=len)
            for name in known:
                if core in name or (title and title[:8] in name):
                    archived = True
                    break
        flag = "已在库" if archived else "★新发现"
        if not archived:
            new.append((p, title, creator, mt, size))
        print(f"{mt} | {size // 1024:6d}KB | {flag} | {title[:42]:42s} | {creator[:20]}")

    print(f"\n新发现 {len(new)} 本")
    if "--copy" in sys.argv:
        H_NEW.mkdir(parents=True, exist_ok=True)
        for p, title, creator, mt, size in new:
            safe = re.sub(r'[\\/:*?"<>|]', "", (title or p.stem))[:80].strip() or p.stem
            dst = H_NEW / f"{safe}.epub"
            if not dst.exists():
                shutil.copy2(p, dst)
        print(f"已复制到 {H_NEW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
