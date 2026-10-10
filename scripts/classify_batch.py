r"""新批次按 Zotero 条目类型分类：Book / CN / En / 学位论文 / 会议论文集。

- 以附件路径（storage: 或链接绝对路径）为键映射回 Zotero 条目类型
- thesis→学位论文；conferencePaper→会议论文集；book/bookSection→Book；
  其余按标题含 CJK 分 CN/En；无 Zotero 映射的按文件名兜底
- 移动到新批次文件夹的对应子目录，重生成分组清单
"""
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
ZOTERO_STORAGE = Path(r"E:\Zotero\storage")
OUT = Path(r"E:\syn\papers_pending_mineru_新批次_20261004")
CATS = ["Book", "CN", "En", "学位论文", "会议论文集", "未识别"]
CJK = re.compile(r"[\u4e00-\u9fff]")

TYPE_MAP = {
    "thesis": "学位论文",
    "conferencePaper": "会议论文集",
    "book": "Book",
    "bookSection": "Book",
}


def main() -> int:
    conn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=30)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT a.path, pt.parentType, COALESCE(pt.parentTitle, '') AS title
        FROM itemAttachments a
        JOIN items ai ON ai.itemID = a.itemID
        LEFT JOIN (
            SELECT pd.itemID AS aid, it.typeName AS parentType, pv.value AS parentTitle
            FROM itemAttachments a2
            JOIN itemData pd ON pd.itemID = a2.parentItemID
            JOIN fields pf ON pf.fieldID = pd.fieldID AND pf.fieldName = 'title'
            JOIN itemDataValues pv ON pv.valueID = pd.valueID
            JOIN itemTypes it ON it.itemTypeID =
                (SELECT itemTypeID FROM items WHERE itemID = a2.parentItemID)
        ) pt ON pt.aid = a.itemID
        WHERE a.contentType = 'application/pdf'
          AND a.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    amap: dict[str, tuple[str, str]] = {}
    for path, ptype, title in cur.fetchall():
        if not path:
            continue
        if path.startswith("storage:"):
            k = path.replace("storage:", "")
        else:
            k = Path(path.replace("file://", "").replace("/", "\\")).name
        amap[k] = (ptype or "", title or "")
    conn.close()
    print(f"Zotero 附件映射 {len(amap)} 条")

    counts = {c: 0 for c in CATS}
    listing = {c: [] for c in CATS}
    for f in sorted(OUT.glob("*.pdf")):
        ptype, title = amap.get(f.name, ("", ""))
        if not ptype and "_" in f.stem:  # 日期前缀的碰撞重名件
            ptype, title = amap.get(re.sub(r"^\d{4}-\d{2}-\d{2}_", "", f.name), ("", ""))
        if not ptype:
            ptype, title = amap.get(f.stem, ("", ""))
        cat = TYPE_MAP.get(ptype)
        if not cat:
            cat = "CN" if CJK.search(title or f.stem) else "En"
            if ptype in ("journalArticle",) and cat == "CN":
                pass
            if not ptype and re.search(r"proceedings|conference|symposium|会议", f.stem, re.I):
                cat = "会议论文集"
        cat = cat if cat in CATS else "未识别"
        sub = OUT / cat
        sub.mkdir(exist_ok=True)
        shutil.move(str(f), str(sub / f.name))
        counts[cat] += 1
        listing[cat].append(f"{title[:70]}（{f.name[:56]}）" if title else f.name[:70])

    print("\n== 解析规模 ==")
    for c in CATS:
        print(f"  {c:8s} {counts[c]:4d} 篇")
        (OUT / f"_清单_{c}.md").write_text(
            f"# {c}（{counts[c]} 篇）\n\n" + "\n".join(listing[c]), encoding="utf-8"
        )
    print(f"\n合计 {sum(counts.values())}，分清单 _清单_*.md 已生成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
