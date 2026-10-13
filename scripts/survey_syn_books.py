r"""盘点 E:\\syn 翻译书籍现状（排除 书籍\\），按入库指南分类行动项。只读。"""
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET

E = Path(r"E:\syn")
EXCLUDE = {"书籍", "papers", "papers_pending_mineru", "papers_pending_mineru_新批次_20261004",
           "_恢复_未识别书目", "_恢复损坏待修", "_references_未挂链", "矿业聚合平台",
           "Calibre 书库", "个人交易研究助手", "小学", "soft", "zlib", "Translatebook",
           "TranslateBook_Data", "mining_epub_work", "__pycache__", "mining_backups",
           "待解析_mineru", "标准整理"}
CJK = re.compile(r"[\u4e00-\u9fff]")


def epub_lang_title(p: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(p) as z:
            c = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            opf = re.search(r'full-path="([^"]+)"', c).group(1)
            root = ET.fromstring(re.sub(r'xmlns="[^"]+"', "", z.read(opf).decode("utf-8", "ignore"), count=1))
            title, lang = "", ""
            for el in root.iter():
                t = el.tag.split("}")[-1]
                if t == "title" and not title:
                    title = (el.text or "").strip()
                if t == "language" and not lang:
                    lang = (el.text or "").strip()
            zh = lang.startswith("zh") or bool(CJK.search(title) or CJK.search(p.name))
            return ("zh" if zh else "en", title)
    except Exception:
        return ("?", "(损坏或无法解析)")
    return ("?", "")


def main() -> int:
    rows = []
    for d in sorted(E.iterdir()):
        if not d.is_dir() or d.name in EXCLUDE:
            continue
        files = list(d.rglob("*"))
        pdfs = [f for f in files if f.suffix.lower() == ".pdf" and f.is_file()]
        mds = [f for f in files if f.suffix.lower() == ".md" and f.is_file()]
        epubs = [f for f in files if f.suffix.lower() == ".epub" and f.is_file()]
        if not (pdfs or mds or epubs):
            continue
        zh_epubs, en_epubs, epub_meta = [], [], {}
        for p in epubs:
            lang, title = epub_lang_title(p)
            epub_meta[p.name] = (lang, title)
            (zh_epubs if lang == "zh" else en_epubs).append(p) if lang != "?" else None
        zh_md = [m for m in mds if m.name.endswith("_zh.md")]
        en_md = [m for m in mds if m.name.endswith("_en.md")]
        other_md = [m for m in mds if not m.name.endswith(("_zh.md", "_en.md"))]
        rows.append({
            "dir": d.name, "pdfs": len(pdfs), "mds": len(mds),
            "zh_md": len(zh_md), "en_md": len(en_md), "other_md": len(other_md),
            "zh_epub": len(zh_epubs), "en_epub": len(en_epubs),
            "epub_meta": epub_meta,
            "newest": max((f.stat().st_mtime for f in files if f.is_file()), default=0),
        })
    print(f"E:\\syn 书目录 {len(rows)} 个（已排除 书籍\\ 与非书籍目录）\n")
    print(f"{'目录':<44s} {'PDF':>3s} {'zh_md':>5s} {'en_md':>5s} {'散md':>4s} {'zh_ep':>5s} {'en_ep':>5s} {'最新修改':<12s}")
    for r in sorted(rows, key=lambda x: -x["newest"]):
        mt = datetime.fromtimestamp(r["newest"]).strftime("%m-%d %H:%M") if r["newest"] else "-"
        print(f"{r['dir'][:42]:44s} {r['pdfs']:3d} {r['zh_md']:5d} {r['en_md']:5d} {r['other_md']:4d} {r['zh_epub']:5d} {r['en_epub']:5d} {mt:<12s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
