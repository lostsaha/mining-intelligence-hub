r"""H:\00\标准整理 的中文露天矿山标准 → md 转换 + 归位 + 入库。

流程：
  1) 扫描 标准整理（.doc/.docx/.pdf），按「标准号+年份」去重（GB 50330 的 doc/docx 取 docx）
  2) 每个标准一个目录：H:\00\mining_library\books\标准-露天矿山\<标准号 名称>\
     内放 原件（doc/docx/pdf）+ <同名>.md
  3) .doc 先经 Word COM 转 .docx（临时），pandoc 转 md 后删临时件；.docx 直接 pandoc
  4) 调 import_books 注册入库（md 分段），PDF-only 的随后由 import_book_pdf 分段
用法：python oneoff_standards_ingest.py [--dry]
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(r"H:\00\标准整理")
DST_ROOT = Path(r"H:\00\mining_library\books\标准-露天矿山")
PANDOC = r"C:\Program Files\Pandoc\pandoc.exe"
PS_MANIFEST = Path(r"E:\syn\矿业聚合平台\scripts\_std_manifest.tsv")
TMP_DIR = Path(r"E:\syn\矿业聚合平台\scripts\_std_tmp")

_KEY_RE = re.compile(r"^((?:GB|GBT|GB/T|DZ|AQ|TCSEB|JTG|MT|SL|DB)[A-Z]*)(\d+)", re.I)


def _key(stem: str) -> str:
    s = re.sub(r"[\s／]+", "", stem)
    m = _KEY_RE.match(s)
    y = re.search(r"(19|20)\d{2}", s)
    if not m:
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", s)[:16]
    code = m.group(1).upper().replace("GBT", "GB").replace("GB/T", "GB") + m.group(2)
    return code + (y.group(0) if y else "")


def _display(stem: str) -> str:
    s = re.sub(r"[《》\[\]]", "", stem)
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    return re.sub(r'[\\/:*?"<>|]', "", s)


def plan() -> list[dict]:
    files = [f for f in sorted(SRC.iterdir())
             if f.suffix.lower() in (".doc", ".docx", ".pdf")
             and not f.name.startswith("~$")]
    best: dict[str, dict] = {}
    for f in files:
        ext = f.suffix.lower()
        rank = {".docx": 3, ".doc": 2, ".pdf": 1}[ext]
        k = _key(f.stem)
        if k in best and rank <= best[k]["rank"]:
            continue
        best[k] = {"key": k, "path": f, "rank": rank, "dup": k in best}
    # 无标准号的文件若与某带号标准的名称互含，视为同一标准（如"爆破振动监测技术规范"⊂TCSEB0008-2019…）
    coded = [v for v in best.values() if _KEY_RE.match(v["path"].stem)]
    out = []
    for v in best.values():
        stem = v["path"].stem
        if not _KEY_RE.match(stem):
            twin = next((c for c in coded
                         if stem in c["path"].stem or c["path"].stem in stem), None)
            if twin is not None and twin is not v:
                continue  # 同名重复
        out.append(v)
    return out


def main() -> int:
    dry = "--dry" in sys.argv
    items = plan()
    print(f"共 {len(list(SRC.iterdir()))} 个文件，去重后 {len(items)} 个标准\n")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    doc_jobs: list[tuple[Path, Path]] = []
    for it in items:
        src, ext = it["path"], it["path"].suffix.lower()
        target_dir = DST_ROOT / _display(src.stem)
        target_dir.mkdir(parents=True, exist_ok=True)
        it["dir"] = target_dir
        if ext == ".pdf":
            it["mode"] = "pdf"
            continue
        md_path = target_dir / (src.stem + ".md")
        it["md"] = md_path
        if ext == ".docx":
            it["mode"] = "docx"
        else:
            it["mode"] = "doc"
            doc_jobs.append((src, TMP_DIR / (src.stem + ".docx")))
        if dry:
            print(f"  [{it['mode']}] {src.name[:60]}")
    if dry:
        print(f"\n.doc 需 Word 转换 {len(doc_jobs)} 个；pdf 直接归位 "
              f"{sum(1 for i in items if i['mode']=='pdf')} 个")
        return 0

    # 1) Word COM 批转 .doc → 临时 .docx
    if doc_jobs:
        PS_MANIFEST.write_text(
            "".join(f"{s}\t{d}\n" for s, d in doc_jobs), encoding="utf-8-sig"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", r"E:\syn\矿业聚合平台\scripts\convert_docs.ps1", str(PS_MANIFEST)],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=1800,
        )
        print(r.stdout[-1500:])
        if r.returncode != 0:
            print("Word 转换退出码", r.returncode, r.stderr[-300:])

    # 2) pandoc → md + 拷原件
    ok = fail = 0
    for it in items:
        src: Path = it["path"]
        d: Path = it["dir"]
        shutil.copy2(src, d / src.name)  # 原件随 md 归档，供核对
        if it["mode"] == "pdf":
            ok += 1
            continue
        tmp_docx = TMP_DIR / (src.stem + ".docx")
        conv = tmp_docx if it["mode"] == "doc" else src
        if not conv.exists():
            print(f"[no-docx] {src.name[:56]}")
            fail += 1
            continue
        r = subprocess.run(
            [PANDOC, "-f", "docx", "-t", "gfm", "--wrap=none",
             "-o", str(it["md"]), str(conv)],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0 and it["md"].stat().st_size > 500:
            ok += 1
        else:
            fail += 1
            print(f"[pandoc-fail] {src.name[:56]}: {(r.stderr or '')[:80]}")
    for t in TMP_DIR.glob("*.docx"):
        t.unlink()  # 清临时件
    print(f"\n转换完成 ok={ok} fail={fail}")

    # 3) 入库（md 分段）
    sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
    from app.documents.import_books import import_books
    stats = import_books(root=DST_ROOT)
    print("入库：", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
