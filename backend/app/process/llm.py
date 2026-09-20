"""OpenAI 兼容接口客户端：相关性判定 + 主题分类 + 中文摘要。"""
from __future__ import annotations

import json
import re

import httpx

from .. import config
from .heuristic import _topics

SYSTEM_PROMPT = """你是矿业工程情报编辑。对给定的行业条目做判定，只输出一个 JSON 对象，不要输出任何其他文字：
{
  "relevant": true/false,          // 是否与矿业工程/矿山运营/矿物加工等真正相关（加密货币挖矿、数据挖掘、纯金融股评一律 false）
  "relevance": 0.0-1.0,            // 矿业相关性
  "topics": ["slug", ...],         // 从候选主题中选 1~3 个最贴切的 slug
  "summary_zh": "一句话中文摘要（30~60字，概括核心内容与行业意义）",
  "item_type": "news|paper|report|conference|company|expert"
}"""

USER_PROMPT_TEMPLATE = """候选主题 slug 列表：
{topic_slugs}

标题：{title}
摘要：{summary}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    # 剥掉可能出现的 markdown 代码围栏
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def classify(title: str, summary: str, site_url: str = "", source_type: str = "news") -> dict:
    valid_slugs = [t["slug"] for t in _topics()]
    prompt = USER_PROMPT_TEMPLATE.format(
        topic_slugs=", ".join(valid_slugs),
        title=title[:400],
        summary=(summary or "（无摘要）")[:1200],
    )
    payload = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    last_error: Exception | None = None
    for _ in range(2):  # 最多重试一次
        try:
            resp = httpx.post(
                f"{config.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                json=payload,
                timeout=45.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = _extract_json(content)

            relevance = max(0.0, min(1.0, float(data.get("relevance", 0))))
            topics = [t for t in (data.get("topics") or []) if t in valid_slugs][:3]
            relevant = bool(data.get("relevant", relevance >= config.RELEVANCE_APPROVE_THRESHOLD))
            return {
                "relevant": relevant,
                "relevance": round(relevance, 2),
                "topics": topics,
                "summary_zh": (data.get("summary_zh") or "").strip()[:160] or None,
                "item_type": data.get("item_type") or "news",
                "reject_reason": None if relevant else "LLM 判定与矿业无关",
            }
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"LLM classify failed: {last_error}")
