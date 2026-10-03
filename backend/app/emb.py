"""可插拔 Embeddings 客户端（OpenAI 兼容 /v1/embeddings）。

环境变量（backend/.env，均未配置时 EMBEDDINGS_ENABLED=False，一切调用安全跳过）：
  EMBEDDINGS_BASE_URL  如 https://api.siliconflow.cn/v1
  EMBEDDINGS_API_KEY   对应服务商的 Key
  EMBEDDINGS_MODEL     如 BAAI/bge-m3（1024 维）
  EMBEDDINGS_DIM       向量维度，须与 sql/010_embeddings.sql 的 vector(1024) 一致，默认 1024
"""
from __future__ import annotations

import httpx

from .. import config

EMBEDDINGS_BASE_URL = config.EMBEDDINGS_BASE_URL
EMBEDDINGS_API_KEY = config.EMBEDDINGS_API_KEY
EMBEDDINGS_MODEL = config.EMBEDDINGS_MODEL
EMBEDDINGS_DIM = config.EMBEDDINGS_DIM
EMBEDDINGS_ENABLED = bool(EMBEDDINGS_BASE_URL and EMBEDDINGS_API_KEY and EMBEDDINGS_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化；任一入参超长自动截断到 ~8000 字符。失败抛 RuntimeError。"""
    if not EMBEDDINGS_ENABLED:
        raise RuntimeError("Embeddings 未配置（EMBEDDINGS_BASE_URL / API_KEY / MODEL）")
    last_error: Exception | None = None
    for _ in range(3):
        try:
            resp = httpx.post(
                f"{EMBEDDINGS_BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {EMBEDDINGS_API_KEY}"},
                json={
                    "model": EMBEDDINGS_MODEL,
                    "input": [t[:8000] for t in texts],
                    "dimensions": EMBEDDINGS_DIM,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            vecs = [d["embedding"] for d in data]
            if len(vecs) != len(texts):
                raise RuntimeError(f"embeddings 数量不符: {len(vecs)} != {len(texts)}")
            if len(vecs[0]) != EMBEDDINGS_DIM:
                raise RuntimeError(
                    f"向量维度 {len(vecs[0])} 与 EMBEDDINGS_DIM={EMBEDDINGS_DIM} 不符"
                    "——请换模型或改 .env 与 sql/010_embeddings.sql 的维度"
                )
            return vecs
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"embeddings 调用失败: {last_error}")
