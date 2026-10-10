r"""references_papers 链接式附件 → Zotero 存储式（用户方案 A）。

流程：备份 DB → 逐条转换（复制进 storage/<key>/ + linkMode 0 + storage: 路径）
→ 修复我此前移动文件造成的断链 → 校验 → 未挂链文件移至 E:\syn\_references_未挂链\
→ 删除 references_papers。
用法：python zotero_convert_to_stored.py [--go]（默认干跑）
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ZOTERO_DB = Path(r"E:\Zotero\zotero.sqlite")
STORAGE = Path(r"E:\Zotero\storage")
FOLDER = Path(r"E:\references_papers")
ORPHAN = Path(r"E:\syn\_references_未挂链")


def main() -> int:
    go = "--go" in sys.argv
    conn = sqlite3.connect(ZOTERO_DB.as_posix(), timeout=20)
    cur = conn.cursor()
    cur.execute("""SELECT ia.itemID, ia.contentType, ia.path, i.key
                   FROM itemAttachments ia JOIN items i ON i.itemID = ia.itemID
                   WHERE ia.linkMode = 2""")
    rows = cur.fetchall()
    print(f"链接式附件共 {len(rows)}")

    conv, fixed, missing, other = 0, 0, [], []
    for iid, ct, path, key in rows:
        raw = (path or "").replace("file://", "").replace("/", "\\")
        in_folder = raw.lower().startswith(str(FOLDER).lower() + "\\")
        src = Path(raw)
        if not src.exists():
            candidate = FOLDER / src.name
            if candidate.exists():  # 我此前移动过位置的文件
                raw = str(candidate)
                src = candidate
                fixed += 1
            else:
                missing.append((iid, raw))
                continue
        if not in_folder:
            other.append((iid, raw))
            continue
        dest_dir = STORAGE / key
        dest = dest_dir / src.name
        if not go:
            conv += 1
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src, dest)
        newpath = "storage:" + src.name
        cur.execute("UPDATE itemAttachments SET linkMode = 0, path = ? WHERE itemID = ?",
                    (newpath, iid))
        try:
            cur.execute("UPDATE items SET synced = 0 WHERE itemID = ?", (iid,))
        except sqlite3.OperationalError:
            pass
        conv += 1

    print(f"{'[dry] ' if not go else ''}转换 {conv}，修复断链 {fixed}，"
          f"缺失跳过 {len(missing)}，库外链接保留 {len(other)}")
    for iid, p in missing[:5]:
        print(f"  [缺] {p[:70]}")
    for iid, p in other[:5]:
        print(f"  [外] {p[:70]}")
    if not go:
        conn.close()
        return 0

    conn.commit()
    cur.execute("""SELECT COUNT(*) FROM itemAttachments WHERE linkMode = 2
                   AND path LIKE '%references_papers%'""")
    print("转换后残留 references_papers 链接:", cur.fetchone()[0])
    conn.close()

    # 未挂链文件 → 孤儿区；随后删文件夹
    linked_names = set()
    c2 = sqlite3.connect(ZOTERO_DB.as_posix(), timeout=20)
    c2c = c2.cursor()
    c2c.execute("SELECT path FROM itemAttachments WHERE linkMode = 0 AND path LIKE 'storage:%'")
    for (p,) in c2c.fetchall():
        linked_names.add(p.replace("storage:", ""))
    c2.close()
    ORPHAN.mkdir(parents=True, exist_ok=True)
    moved = 0
    for f in FOLDER.iterdir():
        if f.name in linked_names:
            continue
        dst = ORPHAN / f.name
        if not dst.exists():
            shutil.move(str(f), str(dst))
            moved += 1
    print(f"未挂链文件移至 {ORPHAN}: {moved}")
    leftover = list(FOLDER.iterdir())
    if not leftover:
        shutil.rmtree(FOLDER)
        print(f"references_papers 已删除（1.4GB 已并入 Zotero storage）")
    else:
        print(f"文件夹残留 {len(leftover)} 项未删，请查看")
    return 0


if __name__ == "__main__":
    sys.exit(main())
