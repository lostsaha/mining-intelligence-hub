r"""图片型表格/公式 → 智谱 GLM-4V 视觉转换 → 原位拼回 md → 重新分段入库。

前置：backend/.env 配 ZHIPU_API_KEY（可选 ZHIPU_VISION_MODEL，默认 glm-4v-flash）
流程：
  1) pandoc --extract-media 重转换（图片引用带正确位置 + 落盘图片文件）
  2) 逐图调视觉模型：表格→GFM 管道表；公式→LaTeX；示意图→一句话；印章/装饰→删除
  3) 原位替换图片引用，删除落盘媒体（过程文件不入 H 盘）
  4) import_books 重新分段入库（幂等）
用法：python vision_ocr_standards.py [--dry] [--limit N] [--model glm-4.5v]
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, r"E:\syn\矿业聚合平台\scripts")
sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from standards_ingest import DST_ROOT, PANDOC, TMP_DIR, _display, plan  # noqa: E402

API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4v-flash"
MEDIA_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)(?:\{[^}]*\})?")
GOOD_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
MIN_BYTES = 2500  # 过小的多为项目符号/线条图标

PROMPT = """这张图片来自中国工程建设标准（doc 文档内嵌图）。请判断类型并只输出转换结果，不要任何解释：
- 表格 → 输出 Markdown 管道表格（GFM），保留全部行列；合并单元格在每行重复填写内容；表头加粗
- 数学公式 → 输出 LaTeX，用 $...$ 包裹
- 流程图/示意图 → 一句中文说明图的内容（30 字内）
- 印章/签名/页眉页脚/装饰 → 输出空字符串
无法辨认时也输出空字符串。"""


def vision_convert(img_path: Path, key: str) -> str:
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    payload = {
        "model": MODEL,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
    }
    last = None
    for _ in range(3):
        try:
            r = httpx.post(
                API, json=payload, timeout=90.0,
                headers={"Authorization": f"Bearer {key}"},
            )
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            last = e
            time.sleep(1.5)
    print(f"    [vision-fail] {img_path.name[:36]}: {str(last)[:60]}")
    return ""


def main() -> int:
    global MODEL
    from app import config  # noqa: F401  先加载 backend/.env 再读 key
    key = os.getenv("ZHIPU_API_KEY", "").strip()
    if "--model" in sys.argv:
        MODEL = sys.argv[sys.argv.index("--model") + 1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    dry = "--dry" in sys.argv
    items = [it for it in plan() if it["path"].suffix.lower() != ".pdf"]
    if limit:
        items = items[:limit]

    if not dry and not key:
        print("未配置 ZHIPU_API_KEY（backend/.env），无法调视觉模型")
        return 1

    sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
    total_ok = total_skip = 0
    for it in items:
        src: Path = it["path"]
        ext = src.suffix.lower()
        d: Path = DST_ROOT / _display(src.stem)
        md_path = d / (src.stem + ".md")
        if ext == ".doc":
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            tmp_docx = TMP_DIR / (src.stem + ".docx")
            manifest = TMP_DIR / "_vision_manifest.tsv"
            manifest.write_text(f"{src}\t{tmp_docx}\n", encoding="utf-8-sig")
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", r"E:\syn\矿业聚合平台\scripts\convert_docs.ps1", str(manifest)],
                capture_output=True, text=True, encoding="gbk", errors="replace", timeout=600,
            )
            conv = tmp_docx
        else:
            conv = src
        if not conv.exists():
            print(f"[no-docx] {src.name[:52]}")
            continue

        media_dir = TMP_DIR / ("_media_" + d.name[:40])
        if media_dir.exists():
            shutil.rmtree(media_dir)
        with_media = TMP_DIR / (d.name[:40] + ".withmedia.md")
        subprocess.run(
            [PANDOC, "-f", "docx", "-t", "markdown", "--wrap=none",
             "--extract-media", str(media_dir), "-o", str(with_media), str(conv)],
            capture_output=True, text=True, timeout=300,
        )
        text = with_media.read_text(encoding="utf-8", errors="ignore")

        refs = MEDIA_RE.findall(text)
        n_img = sum(1 for r in refs if Path(r).suffix.lower() in GOOD_EXTS)
        if dry:
            print(f"[dry] {d.name[:44]:44s} 图片引用 {len(refs):3d}（可识别格式 {n_img}）")
            continue

        ok = skip = 0
        for ref in refs:
            p = Path(ref)
            if not p.is_absolute():
                p = media_dir / ref
            if p.suffix.lower() not in GOOD_EXTS or not p.exists() or p.stat().st_size < MIN_BYTES:
                block = ""
                skip += 1
            else:
                block = vision_convert(p, key)
                ok += 1
                time.sleep(0.3)
            text = MEDIA_RE.sub(lambda m: block if m.group(1) == ref else m.group(0), text, count=1)

        md_path.write_text(text, encoding="utf-8")
        # 过程文件保留在 _std_tmp（用户规则 2026-10-04：便于修补回溯）
        # shutil.rmtree(media_dir, ignore_errors=True)
        # with_media.unlink(missing_ok=True)
        # if ext == ".doc":
        #     conv.unlink(missing_ok=True)
        total_ok += ok
        total_skip += skip
        print(f"[ocr] {d.name[:44]:44s} 转换 {ok:3d} / 跳过 {skip:3d}")
        if limit:
            break

    if dry:
        return 0
    print(f"\n视觉转换完成：转换 {total_ok}，跳过 {total_skip}")
    from app.documents.import_books import import_books
    stats = import_books(root=DST_ROOT)
    print("入库：", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
