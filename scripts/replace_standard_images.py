r"""原位替换标准 docx 中的表格/公式图片 → Word 原生表格与公式，其余保持原件。

- 只替换视觉模型判定为表格(|开头)或公式($...$)的图片；示意图/印章/小图标**保留原图**
- 输出 <标准目录>\<标准名>_图片替换版.docx（原件不动）；.doc 源先经 Word COM 转 docx
- 表格/公式片段由 pandoc 生成（表格补边框），splicing 在 document.xml 上按图元定位
- 结果缓存于 scripts/_std_tmp/img_cache/（断点重跑不重复调视觉 API）
- 用法：python replace_standard_images.py [--limit N] [--fresh]（--fresh 忽略缓存）
"""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, r"E:\syn\矿业聚合平台\scripts")
sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from standards_ingest import DST_ROOT, PANDOC, TMP_DIR, _display, plan  # noqa: E402

API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4v-flash"
CACHE = Path(r"E:\syn\矿业聚合平台\scripts\_std_tmp\img_cache")
GOOD_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MIN_BYTES = 2500
DRAWING_RE = re.compile(r"<w:drawing>.*?</w:drawing>|<w:pict>.*?</w:pict>", re.S)
REF_RE = re.compile(r'(?:r:embed|r:id)="(rId\d+)"')
P_OPEN_RE = re.compile(r"<w:p>|<w:p [^>]*>")
R_OPEN_RE = re.compile(r"<w:r>|<w:r [^>]*>")

PROMPT = """这张图片来自中国工程建设标准（doc 文档内嵌图）。请判断类型并只输出转换结果，不要任何解释：
- 表格 → 输出 Markdown 管道表格（GFM），保留全部行列；合并单元格在每行重复填写内容；表头加粗
- 数学公式 → 输出 LaTeX，用 $...$ 包裹
- 流程图/示意图 → 一句中文说明图的内容（30 字内）
- 印章/签名/页眉页脚/装饰 → 输出空字符串
无法辨认时也输出空字符串。"""


def vision(img_bytes: bytes, key: str) -> str:
    b64 = base64.b64encode(img_bytes).decode()
    payload = {"model": MODEL, "temperature": 0.1, "messages": [
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}]}
    last = None
    for _ in range(6):
        try:
            r = httpx.post(API, json=payload, timeout=120.0,
                           headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 429:
                time.sleep(min(float(r.headers.get("retry-after") or 30), 90))
                continue
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            last = e
            time.sleep(2)
    print(f"    [vision-fail] {str(last)[:60]}")
    return ""


def classify(resp: str) -> tuple[str, str]:
    """→ (table|formula|keep, 内容)——仅表格/公式触发替换，其余一律保留原图。"""
    t = resp.strip()
    lines = [ln for ln in t.splitlines() if ln.strip().startswith("|")]
    if len(lines) >= 2:
        return "table", "\n".join(lines)
    if t.startswith("$") and t.endswith("$") and t.count("$") >= 2:
        return "formula", t
    return "keep", ""


def pandoc_fragment(kind: str, content: str, workdir: Path) -> str:
    """表格/公式 → docx 片段 XML（body 内层），失败返回空串。"""
    src = workdir / "frag.md"
    out = workdir / "frag.docx"
    fmt = "gfm" if kind == "table" else "markdown+tex_math_dollars"
    src.write_text(content if kind == "table" else f"{content}\n", encoding="utf-8")
    r = subprocess.run([PANDOC, "-f", fmt, "-t", "docx", "-o", str(out), str(src)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not out.exists():
        return ""
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8", "ignore")
    m = re.search(r"<w:body>(.*)</w:body>", xml, re.S)
    body = m.group(1) if m else ""
    body = re.sub(r"<w:sectPr.*?</w:sectPr>", "", body, flags=re.S)
    if kind == "table":  # 无样式表也保证有边框
        borders = ("<w:tblBorders>"
                   + "".join(f'<w:{s} w:val="single" w:sz="4" w:color="auto"/>'
                             for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
                   + "</w:tblBorders>")
        if "<w:tblPr>" in body:
            body = body.replace("<w:tblPr>", "<w:tblPr>" + borders, 1)
        else:
            body = body.replace("<w:tbl>", f"<w:tbl><w:tblPr>{borders}</w:tblPr>", 1)
    out.unlink(missing_ok=True)
    return body


def rels_map(z: zipfile.ZipFile) -> dict[str, str]:
    xml = z.read("word/_rels/document.xml.rels").decode("utf-8", "ignore")
    return {m.group(1): m.group(2) for m in re.finditer(
        r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', xml)}


def replace_in_docx(docx_path: Path, out_path: Path, key: str) -> tuple[int, int, int, int]:
    """返回 (检视图片数, 替换表格数, 替换公式数, 保留图片数)。"""
    with zipfile.ZipFile(docx_path) as z:
        names = z.namelist()
        doc_xml = z.read("word/document.xml").decode("utf-8", "ignore")
        blobs = {n: z.read(n) for n in names}
    rels = rels_map(zipfile.ZipFile(docx_path))

    drawings = list(DRAWING_RE.finditer(doc_xml))
    media_order: list[str] = []          # 文档顺序的去重媒体名
    for m in drawings:
        rid = REF_RE.search(m.group(0))
        if not rid:
            continue
        tgt = rels.get(rid.group(1), "")
        name = "word/" + tgt.lstrip("/") if not tgt.startswith("word/") else tgt
        if name not in media_order:
            media_order.append(name)

    CACHE.mkdir(parents=True, exist_ok=True)
    from app import config  # 载入 .env
    import os
    zkey = os.getenv("ZHIPU_API_KEY", "")

    frag_of: dict[str, str] = {}
    n_seen = n_tbl = n_f = n_keep = 0
    for mname in media_order:
        data = blobs.get(mname, b"")
        ext = Path(mname).suffix.lower()
        n_seen += 1
        if ext not in GOOD_EXTS or len(data) < MIN_BYTES:
            n_keep += 1
            continue
        ck = CACHE / (hashlib.md5(f"{key}|{Path(mname).name}|{len(data)}".encode()).hexdigest() + ".json")
        resp = ck.read_text(encoding="utf-8") if ck.exists() and not FRESH else None
        if resp is None:
            resp = vision(data, zkey)
            time.sleep(0.3)
            ck.write_text(resp, encoding="utf-8")
        kind, content = classify(resp)
        if kind == "keep":
            n_keep += 1
            continue
        frag = pandoc_fragment(kind, content, CACHE)
        if not frag:
            n_keep += 1
            continue
        frag_of[mname] = frag
        n_tbl += kind == "table"
        n_f += kind == "formula"

    if not frag_of:
        return n_seen, n_tbl, n_f, n_keep

    # 单次正向遍历：表格与公式都是块级 <w:p>/<w:tbl> 片段，统一按段落处理——
    # 段内还有其他文字时删图元 run、片段插到段落之后；否则整段替换
    out_parts, pos = [], 0
    for m in drawings:
        rid = REF_RE.search(m.group(0))
        s, e = m.span()
        if s < pos:
            continue  # 已被同段前一张图的处理吞掉（AlternateContent 双写/同段多图）
        if not rid or rid.group(1) not in rels:
            continue
        tgt = rels[rid.group(1)]
        name = tgt if tgt.startswith("word/") else "word/" + tgt.lstrip("/")
        frag = frag_of.get(name)
        if not frag:
            continue
        p_open = max(doc_xml.rfind("<w:p>", 0, s), doc_xml.rfind("<w:p ", 0, s))
        p_close = doc_xml.find("</w:p>", e)
        if p_open < 0 or p_close < 0:
            continue  # 结构异常，保留原图
        p_end = p_close + len("</w:p>")
        para_has_text = bool(re.search(r"<w:t[^>]*>[^<]*\S", doc_xml[p_open:s] + doc_xml[e:p_close]))
        if para_has_text:
            r_start = max(doc_xml.rfind("<w:r>", 0, s), doc_xml.rfind("<w:r ", 0, s))
            r_end = doc_xml.find("</w:r>", e)
            if r_start < 0 or r_end < 0:
                continue
            out_parts.append(doc_xml[pos:r_start])
            out_parts.append(doc_xml[r_end + len("</w:r>"):p_end])
            out_parts.append(frag)
            pos = p_end
        else:
            out_parts.append(doc_xml[pos:p_open])
            out_parts.append(frag)
            pos = p_end
    out_parts.append(doc_xml[pos:])
    new_xml = "".join(out_parts)

    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(new_xml)
    except ET.ParseError as exc:
        print(f"    [xml-fail] {docx_path.name[:40]}: {exc}（放弃写盘，保留原图版未生成）")
        return n_seen, n_tbl, n_f, n_keep

    root_fix = ""
    if "xmlns:m=" not in new_xml[:2000]:
        root_fix = ' xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
        new_xml = new_xml.replace("<w:document ", f'<w:document{root_fix} ', 1)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zo:
        for n, data in blobs.items():
            if n == "word/document.xml":
                zo.writestr(n, new_xml)
            else:
                zo.writestr(n, data)
    return n_seen, n_tbl, n_f, n_keep


FRESH = False


def main() -> int:
    global FRESH
    FRESH = "--fresh" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    items = [it for it in plan() if it["path"].suffix.lower() != ".pdf"]
    if limit:
        items = items[:limit]

    # 1) .doc → 临时 docx（Word COM 一批）
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    doc_jobs, conv_of = [], {}
    for it in items:
        src: Path = it["path"]
        if src.suffix.lower() == ".doc":
            t = TMP_DIR / (src.stem + ".docx")
            conv_of[src] = t
            doc_jobs.append((src, t))
        else:
            conv_of[src] = src
    if doc_jobs:
        manifest = TMP_DIR / "_imgrep_manifest.tsv"
        manifest.write_text("".join(f"{s}\t{t}\n" for s, t in doc_jobs), encoding="utf-8-sig")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", r"E:\syn\矿业聚合平台\scripts\convert_docs.ps1", str(manifest)],
                       capture_output=True, text=True, encoding="gbk", errors="replace", timeout=1800)

    # 2) 逐标准替换
    tot = [0, 0, 0, 0]
    done = 0
    for it in items:
        src: Path = it["path"]
        d: Path = DST_ROOT / _display(src.stem)
        conv: Path = conv_of[src]
        if not conv.exists():
            print(f"[no-docx] {d.name[:48]}")
            continue
        out = d / (d.name + "_图片替换版.docx")
        try:
            seen, tbl, f, keep = replace_in_docx(conv, out, d.name)
        except Exception as exc:
            print(f"[fail] {d.name[:48]}: {str(exc)[:80]}")
            continue
        done += 1
        tot[0] += seen; tot[1] += tbl; tot[2] += f; tot[3] += keep
        print(f"[rep] {d.name[:46]:46s} 检视{seen:3d} 表格{tbl:3d} 公式{f:3d} 保留{keep:3d}")

    for t in TMP_DIR.glob("*.docx"):
        t.unlink()
    print(f"\n完成 {done}/{len(items)}：检视图 {tot[0]}，替换表格 {tot[1]}、公式 {tot[2]}，"
          f"保留原图（示意图/印章/小图标）{tot[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
