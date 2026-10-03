r"""把已解析标准的 md 写回 Word（_重建版.docx）：网格/管道表→原生表格，$LaTeX$→OMML 公式。

- 输出：<标准目录>\<标准名>_重建版.docx（原件不动，便于核对）
- 跳过无 md 的标准（扫描件待 MinerU OCR）
- 用法：python rebuild_standards_docx.py [--limit N]
"""
import re
import subprocess
import sys
import zipfile
from pathlib import Path

DST_ROOT = Path(r"H:\00\mining_library\books\标准-露天矿山")
PANDOC = r"C:\Program Files\Pandoc\pandoc.exe"


def docx_stats(p: Path) -> tuple[int, int]:
    try:
        doc = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "ignore")
        return doc.count("<w:tbl>"), len(re.findall(r"<m:oMath[ >]", doc))
    except Exception:
        return 0, 0


def main() -> int:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    mds = sorted(DST_ROOT.glob("*/*.md"))
    if limit:
        mds = mds[:limit]
    total_tbl = total_math = done = 0
    for md in mds:
        out = md.with_name(md.stem + "_重建版.docx")
        r = subprocess.run(
            [PANDOC, str(md), "-f", "markdown+tex_math_dollars", "-o", str(out)],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0 or not out.exists():
            print(f"[fail] {md.parent.name[:48]}: {(r.stderr or '')[:70]}")
            continue
        tbl, math = docx_stats(out)
        total_tbl += tbl
        total_math += math
        done += 1
        print(f"[docx] {md.parent.name[:48]:48s} 表格{tbl:3d} 公式{math:3d}")
    print(f"\n完成 {done}/{len(mds)} 本，Word 原生表格共 {total_tbl} 个、公式共 {total_math} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
