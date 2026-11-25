"""Giới hạn tần suất request theo cửa sổ trượt 60 giây lưu trong Redis (tiêu chí 7)."""
import hashlib
import logging
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent_app")

WINDOW_SECONDS = 60

# Lua script đảm bảo thao tác ZREMRANGEBYSCORE → ZCARD → ZADD → EXPIRE chạy nguyên tử
# giữa nhiều worker uvicorn hoặc nhiều container chạy song song.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local current = redis.call('ZCARD', key)
if current >= limit then
    return {0, current}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return {1, current + 1}
"""


def _rate_limit_key(api_key: str) -> str:
    """Băm API key bằng SHA-256 để không lưu raw secret vào khóa Redis."""
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"rate_limit:{digest}"


def check_rate_limit(key: str) -> None:
    """Kiểm tra số request trong 60 giây gần nhất của API key trên Redis.

    Tham số:
        key: API key hợp lệ đã được xác thực.

    Ngoại lệ:
        HTTPException(429): Khi vượt quá RATE_LIMIT_PER_MINUTE, kèm header Retry-After.
        HTTPException(503): Khi Redis không khả dụng để kiểm tra rate limit.
    """
    if r is None:
        logger.error("rate_limit_backend_missing")
        raise HTTPException(status_code=503, detail="Rate limit backend unavailable")

    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = _rate_limit_key(key)
    member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"

    try:
        result = r.eval(
            _SLIDING_WINDOW_LUA,
            1,
            redis_key,
            str(now),
            str(window_start),
            str(settings.rate_limit_per_minute),
            member,
            str(WINDOW_SECONDS + 5),
        )
    except (redis.RedisError, OSError) as exc:
        logger.error("rate_limit_redis_error: %s", exc)
        raise HTTPException(status_code=503, detail="Rate limit backend unavailable") from exc

    allowed = int(result[0]) if result else 0
    if allowed == 0:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
