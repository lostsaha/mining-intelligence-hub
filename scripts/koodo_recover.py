r"""Koodo 库恢复：9 月后中文成果最新版 → H 盘成果区；导读版两卷登记入库并分段。

- 每个书名组只取 mtime 最新一份（Koodo 里同书多代迭代，最新即最终）
- 导读版（用户手写的中文详解导读）除复制外，注册 document_versions + 分段入 document_chunks
"""
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from app import db  # noqa: E402
from app.documents.import_epub_chunks import epub_chunks  # noqa: E402

BOOK = Path(r"C:\Users\hahn\AppData\Roaming\koodo-reader\uploads\data\book")
BOOKS_H = Path(r"H:\00\mining_library\books")

MAPPING = [  # (Koodo 标题前缀, H 盘书籍目录名)
    ("露天矿爆破原理·第一卷", "Blasting principles for open pit mining"),
    ("露天矿爆破原理·第二卷", "Blasting principles for open pit mining"),
    ("矿山废石场与储矿堆设计指南", "Guidelines for mine waste dump and stockpile design"),
    ("露天矿采矿规划与设计", "Open Pit Mine Planning and Design"),
    ("岩石爆破：工业用岩石爆破方法", "Rock Blasting A Practical Treatise on the Means Employed in Blasting Rocks for Industrial Purposes"),
    ("经济评价与投资决策方法", "Economic Evaluation and Investment Decision Methods"),
    ("Guidelines for Open Pit Slope Design in We", "Guidelines for Open Pit Slope Design in Weak Rocks"),
    ("Guidelines for Open Pit Slope Design (Chin", "Guidelines for Open Pit Slope Design"),
    ("The Mining Valuation Handbook", "The Mining Valuation Handbook 4th Edition Mining And Energy Valuation For Investors And Management"),
    ("Project Management for Mining", "Project management for mining handbook for delivering project success"),
    ("Mineral Resource Estimation", "Mineral Resource Estimation (Mario E. Rossi, Clayton V. Deutsch (auth.))"),
    ("00_SLOPESTABILITY", "Slope stability in surface mining"),
    ("Principles and Practice in Mining Engineer", "Principles and Practice in Mining Engineering.pdf"),
]


def epub_meta(p: Path) -> str:
    import zipfile
    import xml.etree.ElementTree as ET
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


def main() -> int:
    # 1) 扫描 + 按映射分组取最新
    picked: dict[str, tuple[Path, str, float]] = {}  # key -> (path, title, mtime)
    for p in BOOK.glob("*.epub"):
        title = epub_meta(p)
        for key, dirname in MAPPING:
            if title.startswith(key) or title.replace(" ", "").startswith(key.replace(" ", "")):
                mt = p.stat().st_mtime
                if key not in picked or mt > picked[key][2]:
                    picked[key] = (p, title, mt)
                break

    # 2) 复制到 H 盘（命名：中文标题_Koodo最终版.epub）
    dao_versions = []  # (key, path, title)
    for key, dirname in MAPPING:
        if key not in picked:
            print(f"[缺] {key}")
            continue
        p, title, mt = picked[key]
        target = BOOKS_H / dirname
        target.mkdir(parents=True, exist_ok=True)
        date = datetime.fromtimestamp(mt).strftime("%m%d")
        safe = re.sub(r'[\\/:*?"<>|]', "", title)[:70].strip()
        dst = target / f"{safe}_Koodo{date}.epub"
        shutil.copy2(p, dst)
        print(f"[copy] {title[:36]:36s} -> {dirname[:36]} ({p.stat().st_size // 1024}KB)")
        if "露天矿爆破原理" in title:
            dao_versions.append((key, dst, title))

    # 3) 导读版两卷登记入库 + 分段
    doc = db.query_one("SELECT document_id FROM mining.documents WHERE source_dir LIKE %s",
                       ("%Blasting principles%",))
    doc_id = doc["document_id"]
    for key, dst, title in dao_versions:
        v = db.query_one(
            """INSERT INTO mining.document_versions
               (document_id, lang, format, file_path, file_size, parse_status)
               VALUES (%s, 'zh', 'epub', %s, %s, 'pending')
               ON CONFLICT (file_path) DO UPDATE SET parse_status='pending'
               RETURNING version_id""",
            (doc_id, str(dst), dst.stat().st_size),
        )
        version_id = v["version_id"]
        sections = epub_chunks(dst)
        if len(sections) < 3:
            print(f"[warn] {title[:30]} 分段过少({len(sections)})")
            continue
        db.execute("DELETE FROM mining.document_chunks WHERE version_id=%s", (version_id,))
        with db.get_conn() as conn, conn.cursor() as cur:
            for idx, sec in enumerate(sections):
                cur.execute(
                    """INSERT INTO mining.document_chunks
                       (document_id, version_id, lang, chunk_index, section_path, content, char_count)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (doc_id, version_id, "zh", idx, sec["section_path"][:300],
                     sec["content"], len(sec["content"])),
                )
        db.execute("UPDATE mining.document_versions SET parse_status='parsed' WHERE version_id=%s",
                   (version_id,))
        print(f"[入库] {title[:36]}: {len(sections)} 段")

    # 4) 文档标题补中文
    db.execute("UPDATE mining.documents SET title_zh=%s WHERE document_id=%s AND title_zh IS NULL",
               ("露天矿爆破原理（Blasting Principles for Open Pit Mining）", doc_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
