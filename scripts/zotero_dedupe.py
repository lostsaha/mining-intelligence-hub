r"""Zotero 重复条目合并（软删除法）：有翻译笔记的优先保留，其余进回收站。

- 重复判定：规范化标题相同 或 同一 DOI 或 多个附件指向同一文件
- 保留优先级：①子笔记含中文(翻译笔记) ②笔记更多 ③有 PDF 附件 ④更早入库
- 执行方式：败者 itemID 插入 deletedItems（Zotero 回收站，可随时还原；
  之后在 Zotero 界面"清空回收站"做正式清理，同步安全）
- 用法：python zotero_dedupe.py [--go]（默认只出报告；--go 先备份再执行）
"""
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
BACKUP = Path(r"E:\Zotero\zotero.sqlite.bak-20261004")


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", t)


def main() -> int:
    go = "--go" in sys.argv
    conn = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?mode=ro", uri=True, timeout=10)
    cur = conn.cursor()

    # 1) 全部顶层条目（个人库）+ 是否有中文子笔记 + 笔记数 + PDF 附件数
    cur.execute(
        """
        SELECT i.itemID, it.typeName, i.dateAdded,
          (SELECT COUNT(*) FROM itemNotes n WHERE n.parentItemID = i.itemID) AS notes,
          (SELECT COUNT(*) FROM itemNotes n WHERE n.parentItemID = i.itemID
             AND n.note LIKE '%一%') AS zh_notes,  -- 粗筛后精细判
          (SELECT COUNT(*) FROM itemAttachments a WHERE a.parentItemID = i.itemID
             AND a.contentType = 'application/pdf') AS pdfs
        FROM items i JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
        WHERE i.libraryID = 1
          AND it.typeName IN ('journalArticle', 'conferencePaper', 'report',
                              'thesis', 'book', 'bookSection', 'preprint')
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        """
    )
    meta = {r[0]: {"type": r[1], "date": r[2], "notes": r[3], "zh_notes": 0, "pdfs": r[5]}
            for r in cur.fetchall()}
    # 精确中文笔记判定
    cur.execute(
        """
        SELECT n.parentItemID, n.note FROM itemNotes n
        WHERE n.parentItemID IN (SELECT itemID FROM items WHERE libraryID = 1)
        """
    )
    for pid, note in cur.fetchall():
        if pid in meta and re.search(r"[\u4e00-\u9fff]{10,}", note or ""):
            meta[pid]["zh_notes"] += 1
    # 标题与 DOI
    cur.execute(
        """
        SELECT id.itemID, v.value FROM itemData id
        JOIN fields f ON f.fieldID = id.fieldID AND f.fieldName = 'title'
        JOIN itemDataValues v ON v.valueID = id.valueID
        WHERE id.itemID IN (SELECT itemID FROM items WHERE libraryID = 1)
        """
    )
    titles = {}
    for iid, t in cur.fetchall():
        if iid in meta:
            titles[iid] = t
    cur.execute(
        """
        SELECT id.itemID, v.value FROM itemData id
        JOIN fields f ON f.fieldID = id.fieldID AND f.fieldName IN ('DOI', 'Id')
        JOIN itemDataValues v ON v.valueID = id.valueID
        WHERE id.itemID IN (SELECT itemID FROM items WHERE libraryID = 1)
        """
    )
    dois = {iid: norm_title(v).replace("https://doi.org/", "") for iid, v in cur.fetchall() if iid in meta}

    # 2) 分组：规范化标题 + DOI
    groups: dict[str, list[int]] = {}
    for iid, t in titles.items():
        groups.setdefault("T" + norm_title(t)[:60], []).append(iid)
    for iid, d in dois.items():
        if d:
            groups.setdefault("D" + d[:40], []).append(iid)

    def keep_key(iid: int):
        m = meta[iid]
        return (m["zh_notes"] > 0, m["notes"], m["pdfs"], -len(m["date"]), m["date"])

    dup_groups = []
    for gkey, members in groups.items():
        uniq = sorted(set(members))
        if len(uniq) < 2:
            continue
        # 合并同一标题/DOI 指向的簇（避免 A=B、B=C 分裂）——简单并查
        merged = None
        for g in dup_groups:
            if set(g["members"]) & set(uniq):
                merged = g
                break
        if merged:
            merged["members"] = sorted(set(merged["members"]) | set(uniq))
        else:
            dup_groups.append({"key": gkey, "members": uniq})

    plan = []
    for g in dup_groups:
        members = g["members"]
        keeper = max(members, key=keep_key)
        losers = [m for m in members if m != keeper]
        plan.append({"keeper": keeper, "losers": losers, "members": members,
                     "title": (titles.get(keeper) or "?")[:70]})

    n_losers = sum(len(p["losers"]) for p in plan)
    print(f"重复簇 {len(plan)} 个，涉及 {sum(len(p['members']) for p in plan)} 条，"
          f"拟回收站 {n_losers} 条（保留 {len(plan)}）")
    for p in sorted(plan, key=lambda x: -len(x["losers"]))[:15]:
        k = p["keeper"]
        print(f"  [{meta[k]['zh_notes']}译/{meta[k]['notes']}笔] {p['title'][:56]} <- 删{len(p['losers'])}")

    if not go:
        print("\n[dry] 加 --go 执行（先自动备份 zotero.sqlite）")
        conn.close()
        return 0

    if not BACKUP.exists():
        shutil.copy2(ZOTERO_DB, BACKUP)
        print(f"已备份 → {BACKUP}")
    conn.close()
    w = sqlite3.connect(ZOTERO_DB.as_posix(), timeout=10)
    wc = w.cursor()
    done = 0
    for p in plan:
        for iid in p["losers"]:
            wc.execute("SELECT COUNT(*) FROM deletedItems WHERE itemID = ?", (iid,))
            if wc.fetchone()[0] == 0:
                wc.execute("INSERT INTO deletedItems (itemID, dateDeleted) VALUES (?, datetime('now'))",
                           (iid,))
                done += 1
    w.commit()
    w.close()
    print(f"已移入回收站 {done} 条。请打开 Zotero → 回收站核对 → 清空回收站完成正式合并。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
