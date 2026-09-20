"""集中配置：环境变量 + 默认值。不依赖 python-dotenv，自行解析 backend/.env。"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mining:mining_dev_2026@localhost:5432/mining"
)

# LLM（OpenAI 兼容）
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_ENABLED = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)

# 采集设置
COLLECT_MAX_PER_SOURCE = int(os.getenv("COLLECT_MAX_PER_SOURCE", "40"))
PROCESS_BATCH_SIZE = int(os.getenv("PROCESS_BATCH_SIZE", "200"))

# OpenAlex / 专家发现（Phase 2，见 PROJECT_PLAN.md §7）
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "").strip()
EXPERT_FROM_YEAR = int(os.getenv("EXPERT_FROM_YEAR", "2019"))
EXPERT_WORKS_PER_QUERY = int(os.getenv("EXPERT_WORKS_PER_QUERY", "150"))
EXPERT_MIN_WORKS_PER_AUTHOR = int(os.getenv("EXPERT_MIN_WORKS_PER_AUTHOR", "2"))
EXPERT_TOP_N = int(os.getenv("EXPERT_TOP_N", "100"))

DATA_DIR = BACKEND_DIR / "data"

# 评分权重（见 PROJECT_PLAN.md §5.2）
WEIGHTS = {
    "relevance": 0.35,
    "authority": 0.25,
    "freshness": 0.20,
    "depth": 0.20,
}
FRESHNESS_HALF_LIFE_DAYS = 14.0
RELEVANCE_APPROVE_THRESHOLD = 0.5
