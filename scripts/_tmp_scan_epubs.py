r"""盘点未入库的中文 EPUB：全盘扫 → 与 PG 已登记 epub 版本比对 → 未登记清单。"""
import re
import sys
import zipfile
from pathlib import Path

import xml.etree.ElementTree as ET

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import db  # noqa: E402

SCAN = [
    Path(r"E:\syn"),
    Path(r"F:\新建文件夹"),
    Path(r"C:\Users\hahn\AppData\Roaming\koodo-reader\uploads\data\book"),
    Path(r"H:\00\mining_library"),
]
CJK = re.compile(r"[\u4e00-\u9fff]")


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
    registered = {r["file_path"] for r in db.query(
        "SELECT file_path FROM mining.document_versions WHERE format = 'epub'")}
    reg_names = {Path(p).name for p in registered}
    reg_titles = set()
    for r in db.query("SELECT title_zh, title_en FROM mining.documents"):
        for v in (r["title_zh"], r["title_en"]):
            if v:
                reg_titles.add(re.sub(r"\s+", "", v)[:20])

    seen_titles: set[str] = set()
    unreg = []
    total = 0
    for area in SCAN:
        if not area.exists():
            continue
        for p in area.rglob("*.epub"):
            total += 1
            if str(p) in registered or p.name in reg_names:
                continue
            title = epub_title(p)
            tkey = re.sub(r"\s+", "", title)[:20]
            is_zh = bool(CJK.search(p.name) or CJK.search(title))
            if tkey and tkey in reg_titles:
                continue  # 同书不同代文件，标题已在库
            if not is_zh:
                continue  # 只关注中文成果
            if tkey in seen_titles:
                continue
            seen_titles.add(tkey)
            unreg.append((p, title))
    print(f"扫描 epub {total} 个，未登记中文成果 {len(unreg)} 本\n")
    for p, t in sorted(unreg, key=lambda x: -x[0].stat().st_mtime):
        import datetime
        mt = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
        print(f"{mt} | {p.stat().st_size // 1048576:3d}MB | {t[:36]:36s} | {str(p)[:66]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
