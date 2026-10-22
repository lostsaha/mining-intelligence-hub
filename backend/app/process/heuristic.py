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
    "moon mining", "lunar mining", "asteroid mining",
    "moon", "lunar", "asteroid",
]
HARD_NOISE = {"moon", "lunar", "asteroid"}

# 强矿业语境词：单独出现也能说明是矿业工程/矿山运营，而不是金属价格或电池需求。
MINING_CONTEXT_WORDS = [
    "mine", "mining", "miner", "ore", "mineral", "pit", "open-pit", "openpit",
    "tailings", "blast", "geotech", "haul", "crusher", "concentrator",
    "smelter", "refinery", "drill core", "drill hole", "drill result",
    "processing plant", "beneficiation", "comminution", "ventilation",
    "dewatering", "slope stability", "rock mechanics", "backfill", "shaft",
    "adit", "stope", "underground", "concentrate", "waste rock", "overburden",
    "reclamation", "mine closure", "acid mine drainage", "haul road",
    "mineral resource", "ore reserve", "resource estimate", "feasibility study",
    "recovery circuit", "ore body", "orebody", "grade control",
    "leach", "leaching", "flotation", "gravity separation",
    "mine plan", "mine life", "life of mine", "strip ratio", "cut-off grade",
    "矿山", "采矿", "矿业", "矿床", "选矿", "钻孔", "爆破", "尾矿",
    "露天矿", "地下矿", "矿井", "巷道", "采场", "充填", "通风", "排水",
    "边坡", "岩层", "储量", "资源量", "品位", "产能", "选厂", "冶炼",
]

# 这些词在金融/宏观新闻里也很常见，单独出现不足以证明矿山语境。
GENERIC_CONTEXT_WORDS = {
    "deposit", "resource", "reserve", "grade", "tonnage",
    "feasibility", "throughput", "recovery",
}

# 矿种/金属品类：单独出现不足以判定为矿业工程（可能是价格、股评、电池需求）。
COMMODITY_WORDS = [
    "gold", "copper", "lithium", "nickel", "cobalt", "silver", "zinc",
    "uranium", "iron ore", "bauxite", "alumina", "coal", "platinum",
    "palladium", "rare earth", "graphite", "manganese", "tin ", "tungsten",
    "molybdenum", "potash", "phosphate", "diamond", "steelmaking coal",
    "铁矿", "铜矿", "金矿", "银矿", "锂矿", "煤矿", "铀矿", "铝土", "稀土",
]

# 主要矿业公司：标题常只出现公司名，但需配合语境词或公司类信源。
COMPANY_WORDS = [
    "newmont", "barrick", "rio tinto", "bhp", "vale", "anglo american",
    "glencore", "teck", "freeport", "anglogold", "gold fields", "kinross",
    "alcoa", "south32", "newcrest",
    "紫金矿业", "洛阳钼业", "中煤", "神华",
]

# 兼容旧引用
BASE_MINING_WORDS = MINING_CONTEXT_WORDS + COMMODITY_WORDS + COMPANY_WORDS

# 纯财经/股评线索：即使出现 mining/company，也不足以证明是矿山运营内容。
FINANCE_WORDS = [
    "stock", "stocks", "share", "shares", "dividend", "rally", "market cap",
    "valuation", "investor", "investors", "earnings", "revenue", "profit",
    "price target", "analyst", "nasdaq", "nyse", "tsx",
]
PROJECT_WORDS = [
    "expansion", "project", "development", "construction", "commissioning",
    "production start", "first production", "mine plan", "plant",
    "approval", "approved", "approves", "permit",
]

_PAPER_DOMAINS = ("mdpi.com", "springer.com", "sciencedirect", "onlinelibrary.wiley", "tandfonline")

# 这些关键词只说明“矿种/市场”，单独命中不足以证明是矿业工程新闻。
WEAK_TOPIC_KEYWORDS = {w.strip() for w in COMMODITY_WORDS} | {
    "critical minerals", "energy transition", "battery minerals",
    "commodity price", "market", "demand", "supply", "price", "trade",
    "recovery", "resource", "reserve", "grade", "tonnage",
    "feasibility", "throughput", "deposit",
    "machine learning", "deep learning", "neural network", "artificial intelligence",
    "optimization", "prediction", "classification", "clustering", "simulation",
    "big data", "assessment", "review", "numerical modeling", "numerical simulation",
    "关键矿产", "能源转型", "电池矿产", "锂", "钴", "镍", "稀土", "铜矿",
}


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

    noise_hits = [w for w in NOISE_KEYWORDS if _contains(text, w)]
    context_hits = [w for w in MINING_CONTEXT_WORDS if _contains(text, w)]
    strong_context_hits = [w for w in context_hits if w not in GENERIC_CONTEXT_WORDS]
    commodity_hits = [w for w in COMMODITY_WORDS if _contains(text, w)]
    company_hits = [w for w in COMPANY_WORDS if _contains(text, w)]
    finance_hits = [w for w in FINANCE_WORDS if _contains(text, w)]
    project_hits = [w for w in PROJECT_WORDS if _contains(text, w)]
    company_project = bool(company_hits and project_hits)

    # 主题匹配（按命中关键词数量排序；区分“矿业语境词”和“矿种/市场词”）
    topic_scores = []
    specific_topic_hits = 0
    for topic in _topics():
        hits = [k for k in topic["keywords"] if k in text]
        if hits:
            specific = [k for k in hits if k not in WEAK_TOPIC_KEYWORDS]
            specific_topic_hits += len(specific)
            topic_scores.append((topic["slug"], len(hits)))
    topic_scores.sort(key=lambda x: -x[1])
    topics = [slug for slug, _ in topic_scores[:3]]

    if any(w in HARD_NOISE for w in noise_hits):
        return {"relevant": False, "relevance": 0.15, "topics": [],
                "reject_reason": "噪音主题（太空/小行星采矿等非 terrestrial 矿业）"}

    if noise_hits and not topics and len(context_hits) <= 1:
        return {"relevant": False, "relevance": 0.15, "topics": [],
                "reject_reason": f"噪音主题（{', '.join(noise_hits[:3])}）"}

    # 纯财经/股评：只有“mining”或公司名、没有具体矿山/项目语境时拒绝。
    if finance_hits:
        non_finance_context = [
            w for w in strong_context_hits
            if w not in {"mine", "mining", "miner", "mineral"}
        ]
        if not non_finance_context and not company_project:
            return {"relevant": False, "relevance": 0.35, "topics": [],
                    "reject_reason": "财经/股评内容，缺少具体矿山运营或项目语境"}

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

    # 仅有矿种/金属、公司名或市场主题、没有矿山语境：多为价格、股评、电池需求类新闻。
    # recovery/resource/reserve 等泛词单独出现不算强语境，避免“金价回升”被误收。
    if not strong_context_hits and not specific_topic_hits and not company_project:
        if context_hits or commodity_hits or company_hits or topics:
            return {"relevant": False, "relevance": 0.35, "topics": [],
                    "reject_reason": "仅命中矿种/市场/泛化词，缺少矿山运营或矿业工程语境"}
        return {"relevant": False, "relevance": 0.2, "topics": [],
                "reject_reason": "未命中矿业相关词根"}

    # 相关性：强语境词为主，矿种/主题密度只做小幅加权
    relevance = 0.60 if (strong_context_hits or company_project) else 0.55
    relevance += 0.05 * min(3, max(0, len(strong_context_hits) - 1))
    relevance += 0.02 * min(2, len(commodity_hits))
    relevance += 0.05 * min(4, len(topic_scores))
    relevance = min(0.95, relevance)

    domain = (site_url or "").lower()
    item_type = "paper" if any(d in domain for d in _PAPER_DOMAINS) or source_type == "journal" else "news"

    return {
        "relevant": relevance >= config.RELEVANCE_APPROVE_THRESHOLD,
        "relevance": round(relevance, 2),
        "topics": topics,
        "item_type": item_type,
        "reject_reason": None if relevance >= config.RELEVANCE_APPROVE_THRESHOLD else "矿业相关性不足",
    }
