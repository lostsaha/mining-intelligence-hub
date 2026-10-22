"""轻量安全工具：管理端点保护、客户端识别、进程内限流。

单机 MVP 用内存桶即可；多 worker / 多机部署时应替换为 Redis 或网关限流。
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_buckets: dict[str, deque[float]] = defaultdict(deque)
_bucket_lock = threading.Lock()

_LOOPBACKS = {"127.0.0.1", "::1", "localhost", "testclient"}


def client_ip(request: Request) -> str:
    """取客户端 IP。仅信任直连地址，不解析可伪造的 X-Forwarded-For。"""
    return request.client.host if request.client else "unknown"


def client_hash(request: Request) -> str:
    """用于问答日志的去标识化客户端指纹（IP + UA），不存原文。"""
    raw = f"{client_ip(request)}|{request.headers.get('user-agent', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def rate_limit(key: str, limit_per_min: int) -> None:
    """滑动窗口限流；limit<=0 表示关闭。"""
    if limit_per_min <= 0:
        return
    now = time.monotonic()
    with _bucket_lock:
        bucket = _buckets[key]
        cutoff = now - 60.0
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit_per_min:
            retry_after = max(1, int(60 - (now - bucket[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请 {retry_after} 秒后重试",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


def require_admin(request: Request) -> None:
    """保护付费/有副作用的管理端点。

    规则：
    1. 配置了 ADMIN_TOKEN：必须提供匹配的 X-Admin-Token；
    2. 未配置 ADMIN_TOKEN 且 ADMIN_ALLOW_LOOPBACK=1：仅允许本机回环地址，
       并要求自定义头 X-Requested-With: mining-admin（阻止跨站简单请求）；
    3. 其余情况拒绝，提示管理员显式配置。
    """
    if config.ADMIN_TOKEN:
        supplied = request.headers.get("x-admin-token", "")
        if not hmac.compare_digest(supplied, config.ADMIN_TOKEN):
            raise HTTPException(401, "管理令牌无效")
    elif config.ADMIN_ALLOW_LOOPBACK:
        if client_ip(request) not in _LOOPBACKS:
            raise HTTPException(403, "管理端点仅允许本机访问；请配置 ADMIN_TOKEN")
        if request.headers.get("x-requested-with") != "mining-admin":
            raise HTTPException(403, "缺少管理请求标记（X-Requested-With: mining-admin）")
    else:
        raise HTTPException(503, "管理端点未启用：请配置 ADMIN_TOKEN")

    rate_limit(f"admin:{client_ip(request)}", config.ADMIN_RATE_LIMIT_PER_MIN)


def require_ask_quota(request: Request) -> None:
    """问答端点按客户端 IP 限流，防止 LLM 费用被刷。"""
    rate_limit(f"ask:{client_ip(request)}", config.ASK_RATE_LIMIT_PER_MIN)
