"""关键词启发式过滤：无 LLM 时的回退方案。

目标不是精确理解，而是挡住明显噪音（加密货币挖矿、数据挖掘等）并给出
粗粒度的主题归属，保证管线开箱可跑。
"""
from __future__ import annotations

import re

from .. import config

# 与矿业工程无关的 "mining" 歧义噪音
NOISE_KEYWORDS = [
    "crypto", "bitcoin", "ethereum", "blockchain", "nft", "solana",
    "coin", "token", "mining rig", "mining pool", "hash rate", "hashrate",
    "data mining", "process mining", "text mining", "opinion mining",
    "gpu mining", "asic miner", "web3", "kaspersky", "antivirus",
    "asteroid mining company stocktip", "minecraft",
]

# 基础矿业词根：命中才认为与矿业工程相关（含大宗矿种/金属品类）
BASE_MINING_WORDS = [
    "mine", "mining", "miner", "ore", "mineral", "pit", "open-pit", "openpit",
    "tailings", "blast", "geotech", "haul", "crusher", "concentrator",
    "gold", "copper", "lithium", "nickel", "cobalt", "silver", "zinc",
    "uranium", "iron ore", "bauxite", "alumina", "coal", "platinum",
    "palladium", "rare earth", "graphite", "manganese", "tin ", "tungsten",
    "molybdenum", "potash", "phosphate", "diamond", "steelmaking coal",
    "smelter", "refinery", "drill core", "drill hole", "drill result",
    # 主要矿业公司（新闻标题常只出现公司名）
    "newmont", "barrick", "rio tinto", "bhp", "vale", "anglo american",
    "glencore", "teck", "freeport", "anglogold", "gold fields", "kinross",
    "alcoa", "south32", "newcrest",
    "紫金矿业", "洛阳钼业", "中煤", "神华",
    "矿山", "采矿", "矿业", "矿床", "选矿", "钻孔", "爆破",
    "铁矿", "铜矿", "金矿", "银矿", "锂矿", "煤矿", "铀矿", "铝土", "稀土",
]

_PAPER_DOMAINS = ("mdpi.com", "springer.com", "sciencedirect", "onlinelibrary.wiley", "tandfonline")


def _load_topic_keywords() -> list[dict]:
    import yaml
    with (config.DATA_DIR / "topics.yaml").open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [
        {"slug": t["slug"], "keywords": [k.lower() for k in t.get("keywords", [])]}
        for t in data["topics"]
    ]


_TOPIC_CACHE: list[dict] | None = None


def _topics() -> list[dict]:
    global _TOPIC_CACHE
    if _TOPIC_CACHE is None:
        _TOPIC_CACHE = _load_topic_keywords()
    return _TOPIC_CACHE


def _contains(text: str, needle: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", needle):
        return needle in text
    # 英文短语按词边界匹配
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text) is not None


def classify(title: str, summary: str, site_url: str = "", source_type: str = "news") -> dict:
    """返回 {relevant, relevance, topics, summary_zh, item_type, reject_reason}。"""
    text = f"{title} {summary}".lower()

    noise_hits = [w for w in NOISE_KEYWORDS if w in text]
    base_hits = [w for w in BASE_MINING_WORDS if _contains(text, w)]

    # 主题匹配（按命中关键词数量排序）
    topic_scores = []
    for topic in _topics():
        hits = sum(1 for k in topic["keywords"] if k in text)
        if hits > 0:
            topic_scores.append((topic["slug"], hits))
    topic_scores.sort(key=lambda x: -x[1])
    topics = [slug for slug, _ in topic_scores[:3]]

    if noise_hits and not topics and len(base_hits) <= 1:
        return {"relevant": False, "relevance": 0.15, "topics": [],
                "reject_reason": f"噪音主题（{', '.join(noise_hits[:3])}）"}

    # 公司类信源本身是"公司名+mine"的定向查询，内容与矿业相关是既定前提：
    # 只要不是噪音，就给相关性保底，避免标题只出现公司名时被误拒。
    if source_type == "company":
        if noise_hits:
            return {"relevant": False, "relevance": 0.2, "topics": [],
                    "reject_reason": f"噪音主题（{', '.join(noise_hits[:3])}）"}
        relevance = 0.65
        if topics:
            return {"relevant": True, "relevance": relevance, "topics": topics,
                    "item_type": "company", "reject_reason": None}
        return {"relevant": True, "relevance": relevance, "topics": ["industry"],
                "item_type": "company", "reject_reason": None}

    if not base_hits and not topics:
        return {"relevant": False, "relevance": 0.2, "topics": [],
                "reject_reason": "未命中矿业相关词根"}

    # 相关性：基础词根 + 主题关键词密度
    relevance = 0.55 + 0.05 * min(3, len(base_hits) - 1) + 0.05 * min(4, len(topic_scores))
    relevance = min(0.9, relevance)

    domain = (site_url or "").lower()
    item_type = "paper" if any(d in domain for d in _PAPER_DOMAINS) or source_type == "journal" else "news"

    return {
        "relevant": relevance >= config.RELEVANCE_APPROVE_THRESHOLD,
        "relevance": round(relevance, 2),
        "topics": topics,
        "item_type": item_type,
        "reject_reason": None if relevance >= config.RELEVANCE_APPROVE_THRESHOLD else "矿业相关性不足",
    }
