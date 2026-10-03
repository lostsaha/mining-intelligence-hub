r"""智谱 key 探测：视觉两档模型对比一张表图 + embedding-3 维度验证。"""
import base64
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import config  # noqa: E402,F401  载入 .env

import os  # noqa: E402

KEY = os.getenv("ZHIPU_API_KEY", "")
API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

PROMPT = """这张图片来自中国工程建设标准（doc 文档内嵌图）。请判断类型并只输出转换结果，不要任何解释：
- 表格 → 输出 Markdown 管道表格（GFM），保留全部行列；合并单元格在每行重复填写内容；表头加粗
- 数学公式 → 输出 LaTeX，用 $...$ 包裹
- 流程图/示意图 → 一句中文说明图的内容（30 字内）
- 印章/签名/页眉页脚/装饰 → 输出空字符串
无法辨认时也输出空字符串。"""

SRC = next(iter(Path(r"H:\00\标准整理").glob("*50330*.docx")))
MEDIA = Path(r"E:\syn\矿业聚合平台\scripts\_probe_media")


def call(model: str, img: Path) -> str:
    b64 = base64.b64encode(img.read_bytes()).decode()
    r = httpx.post(API, timeout=120.0, headers={"Authorization": f"Bearer {KEY}"},
                   json={"model": model, "temperature": 0.1, "messages": [{"role": "user", "content": [
                       {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                       {"type": "text", "text": PROMPT}]}]})
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()


def main() -> None:
    if MEDIA.exists():
        shutil.rmtree(MEDIA)
    with zipfile.ZipFile(SRC) as z:
        media = sorted((n, z.getinfo(n).file_size) for n in z.namelist()
                       if n.startswith("word/media/") and n.lower().endswith((".png", ".jpg", ".jpeg")))
        media.sort(key=lambda x: -x[1])
        print("源内嵌图 top3:", [(n.rsplit('/', 1)[-1], f"{s//1024}KB") for n, s in media[:3]])
        MEDIA.mkdir(parents=True)
        for n, _ in media[:3]:
            (MEDIA / Path(n).name).write_bytes(z.read(n))

    img = MEDIA / Path(media[0][0]).name
    for model in ("glm-4v-flash", "glm-4.5v"):
        try:
            out = call(model, img)
            print(f"\n===== {model} 输出（前600字） =====\n{out[:600]}")
        except Exception as e:
            print(f"\n===== {model} 不可用: {str(e)[:120]}")

    from app import emb
    v = emb.embed(["露天矿边坡稳定监测"])
    print(f"\nembedding-3: 维度={len(v[0])} (EMBEDDINGS_DIM={emb.EMBEDDINGS_DIM})")


if __name__ == "__main__":
    main()
