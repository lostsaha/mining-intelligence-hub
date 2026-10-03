"""抓取智谱 429 完整报错体：embedding-3 / glm-4.5v（标准端点）+ coding 端点可用性。"""
import sys

import httpx

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")
from app import config  # noqa: E402,F401

import os  # noqa: E402

KEY = os.getenv("ZHIPU_API_KEY", "")
STD = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
CODING = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
EMB = "https://open.bigmodel.cn/api/paas/v4/embeddings"


def post(url: str, payload: dict, label: str) -> None:
    try:
        r = httpx.post(url, json=payload, timeout=60.0,
                       headers={"Authorization": f"Bearer {KEY}"})
        body = r.json() if "json" in r.headers.get("content-type", "") else r.text
        if r.status_code == 200:
            c = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[{label}] 200 OK，输出前60字: {str(c)[:60]}")
        else:
            print(f"[{label}] {r.status_code}: {str(body)[:260]}")
    except Exception as e:
        print(f"[{label}] 异常: {str(e)[:140]}")


post(EMB, {"model": "embedding-3", "input": ["边坡稳定"]}, "embedding-3 标准端点")
post(STD, {"model": "glm-4.5v", "messages": [{"role": "user", "content": "hi"}]}, "glm-4.5v 标准端点")
post(STD, {"model": "glm-4v-flash", "messages": [{"role": "user", "content": "回复ok"}]}, "glm-4v-flash 标准端点")
post(CODING, {"model": "glm-4.6", "messages": [{"role": "user", "content": "回复ok"}]}, "glm-4.6 coding端点")
