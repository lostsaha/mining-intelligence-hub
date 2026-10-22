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
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))

# LLM（OpenAI 兼容）
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_ENABLED = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "800"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "90"))

# 前端来源：默认同时允许 3000/3100，避免文档端口不一致导致 CORS 失败
CORS_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3100,http://127.0.0.1:3100",
    ).split(",") if o.strip()
]

# 管理端点保护：
# - ADMIN_TOKEN 非空时，必须带 X-Admin-Token；
# - ADMIN_TOKEN 为空时，仅允许本机回环地址 + X-Requested-With: mining-admin
#   （阻止任意网页通过表单/简单请求触发付费管线）。
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
ADMIN_ALLOW_LOOPBACK = os.getenv("ADMIN_ALLOW_LOOPBACK", "1").strip() == "1"

# 简单的进程内限流（单机 MVP；多 worker/多机需换 Redis）
ASK_RATE_LIMIT_PER_MIN = int(os.getenv("ASK_RATE_LIMIT_PER_MIN", "20"))
ADMIN_RATE_LIMIT_PER_MIN = int(os.getenv("ADMIN_RATE_LIMIT_PER_MIN", "3"))

APP_VERSION = "0.2.0"

# Embeddings（OpenAI 兼容 /embeddings，Phase 4D 语义检索；未配置则关闭）
EMBEDDINGS_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "").rstrip("/")
EMBEDDINGS_API_KEY = os.getenv("EMBEDDINGS_API_KEY", "").strip()
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "").strip()
EMBEDDINGS_DIM = int(os.getenv("EMBEDDINGS_DIM", "1024"))
# 仅部分服务商支持 dimensions 入参（如智谱 embedding-3）；硅基流动 bge-m3 传了会 400
EMBEDDINGS_SEND_DIM = os.getenv("EMBEDDINGS_SEND_DIM", "").strip() == "1"

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
