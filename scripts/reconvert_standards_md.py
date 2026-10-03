r"""标准 md 质量优化：gfm 重转换为 pandoc markdown（网格表格+LaTeX 公式），
诊断图片型表格/公式规模，并为图片重的标准生成 MinerU OCR 移交 PDF。

流程：
  1) 记录旧 md 指标（图片引用/表格行/公式）
  2) .doc → 临时 docx（Word COM 复用）
  3) pandoc -t markdown 重转换（临时 docx 顺手导出 PDF 到 standards_ocr，若图片多）
  4) 重新 import_books 分段入库（幂等）
  5) 输出新旧对比报告
用法：python reconvert_standards_md.py
"""
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, r"E:\syn\矿业聚合平台\scripts")
sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from standards_ingest import (  # noqa: E402
    DST_ROOT, PS_MANIFEST, PANDOC, TMP_DIR, _display, plan,
)

OCR_DIR = Path(r"H:\00\mining_library\papers_pending_mineru\standards_ocr")
MEDIA_HEAVY = 5  # docx 内嵌图片 ≥ 此数 → 生成 MinerU 移交 PDF


def docx_stats(p: Path):
    """(真表格数, 公式数, 内嵌图片数)——docx 为 zip 可直读。"""
    try:
        with zipfile.ZipFile(p) as z:
            doc = z.read("word/document.xml").decode("utf-8", "ignore")
            media = sum(1 for n in z.namelist() if n.startswith("word/media/"))
            return doc.count("<w:tbl>"), len(re.findall(r"<m:oMath[ >]", doc)), media
    except Exception:
        return 0, 0, 0


def md_stats(p: Path):
    """(字符数, 图片引用, 表格行, 数学串)"""
    if not p.exists():
        return 0, 0, 0, 0
    t = p.read_text(encoding="utf-8", errors="ignore")
    imgs = len(re.findall(r"!\[[^\]]*\]\(", t))
    rows = sum(1 for ln in t.splitlines()
               if re.match(r"^\s*\|.*\|\s*$", ln) or re.match(r"^\s*\+[-=+]+\+\s*$", ln))
    math = len(re.findall(r"\$[^$\n]+\$", t))
    return len(t), imgs, rows, math


def main() -> int:
    items = plan()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"标准数 {len(items)}\n== 1) 旧 md 指标 ==")

    doc_jobs = []
    for it in items:
        src: Path = it["path"]
        d: Path = DST_ROOT / _display(src.stem)
        it["dir"] = d
        it["md"] = d / (src.stem + ".md")
        it["old"] = md_stats(it["md"])
        if src.suffix.lower() == ".doc":
            it["tmp_docx"] = TMP_DIR / (src.stem + ".docx")
            doc_jobs.append((src, it["tmp_docx"]))

    # Word COM 批转 .doc → 临时 docx
    if doc_jobs:
        PS_MANIFEST.write_text(
            "".join(f"{s}\t{t}\n" for s, t in doc_jobs), encoding="utf-8-sig"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", r"E:\syn\矿业聚合平台\scripts\convert_docs.ps1", str(PS_MANIFEST)],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=1800,
        )

    print("== 2) pandoc 重转换 (-t markdown) ==")
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    ocr_list = []
    better = worse = 0
    report = []
    for it in items:
        src: Path = it["path"]
        ext = src.suffix.lower()
        if ext == ".pdf":
            continue
        conv: Path = it.get("tmp_docx", src)
        if not conv.exists():
            print(f"[no-docx] {src.name[:52]}")
            continue
        tbl, math, media = docx_stats(conv)
        subprocess.run(
            [PANDOC, "-f", "docx", "-t", "markdown", "--wrap=none",
             "-o", str(it["md"]), str(conv)],
            capture_output=True, text=True, timeout=300,
        )
        new = md_stats(it["md"])
        gain_tables = new[2] - it["old"][2]
        gain_math = new[3] - it["old"][3]
        better += gain_tables + gain_math > 0
        worse += gain_tables < -20
        report.append((src.stem[:40], tbl, math, media, it["old"], new))
        # 图片重 → 导出 PDF 交 MinerU OCR
        if media >= MEDIA_HEAVY and not (it["md"].exists() and new[1] == 0):
            pdf_path = OCR_DIR / (_display(src.stem) + ".pdf")
            if not pdf_path.exists():
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
                     f"$doc=$w.Documents.Open('{conv}', $false, $true);"
                     f"$doc.SaveAs2('{pdf_path}', 17);$doc.Close($false);$w.Quit()"],
                    capture_output=True, text=True, timeout=300,
                )
            ocr_list.append(src.stem[:44])

    for t in TMP_DIR.glob("*.docx"):
        t.unlink()

    print("\n== 3) 对比报告（标准 | 源: 表格/公式/图片 | 旧md: 字/图/表行/式 | 新md: 字/图/表行/式）==")
    for stem, tbl, math, media, old, new in report:
        flag = " ←改善" if new[2] > old[2] + 5 or new[3] > old[3] + 5 else ""
        print(f"  {stem:42s} 源 {tbl:3d}/{math:3d}/{media:3d} | "
              f"旧 {old[0]//1000:4d}k/{old[1]:3d}/{old[2]:4d}/{old[3]:3d} → "
              f"新 {new[0]//1000:4d}k/{new[1]:3d}/{new[2]:4d}/{new[3]:3d}{flag}")

    print("\n== 4) 重新分段入库 ==")
    from app.documents.import_books import import_books
    stats = import_books(root=DST_ROOT)
    print("入库：", stats)

    # 扫描件 PDF 一并列入 OCR 清单
    scanned = [p.stem for p in DST_ROOT.rglob("*.pdf") if p.suffix == ".pdf"
               and "15663" not in p.stem]
    (OCR_DIR / "_待OCR清单.md").write_text(
        "# 待 MinerU OCR 的标准 PDF\n\n"
        "## 图片型表格/公式标准（doc 导出）\n"
        + "".join(f"- {s}\n" for s in sorted(set(ocr_list)))
        + "\n## 扫描件标准（无文字层）\n"
        + "".join(f"- {s}\n" for s in sorted(set(scanned)))
        + "\n\nMinerU 输出 md 放回对应标准目录（<标准名>.md），然后重跑\n"
          "`python -m app.documents.import_books`（md 会替换 failed 的 pdf 版本分段）。\n",
        encoding="utf-8",
    )
    print(f"\nMinerU 移交 PDF：{OCR_DIR}（{len(ocr_list)} 个 doc 导出 + {len(scanned)} 个扫描件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
