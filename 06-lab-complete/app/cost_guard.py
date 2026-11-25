"""Kiểm soát chi phí gọi LLM theo ngân sách ngày/tháng lưu trong Redis (tiêu chí 8)."""
import logging
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent_app")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

DAILY_TTL_SECONDS = 2 * 24 * 3600
MONTHLY_TTL_SECONDS = 32 * 24 * 3600


def _budget_keys() -> tuple[str, str]:
    """Tạo cặp khóa Redis theo ngày và tháng hiện tại (giờ UTC)."""
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def check_budget() -> None:
    """Kiểm tra tổng chi phí đã dùng trước khi gọi LLM.

    Ngoại lệ:
        HTTPException(402): Khi tổng chi phí chạm hoặc vượt DAILY_BUDGET_USD / MONTHLY_BUDGET_USD.
        HTTPException(503): Khi Redis không khả dụng.
    """
    if r is None:
        logger.error("cost_guard_backend_missing")
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable")

    daily_key, monthly_key = _budget_keys()
    try:
        daily_raw, monthly_raw = r.mget(daily_key, monthly_key)
    except (redis.RedisError, OSError) as exc:
        logger.error("cost_guard_read_error: %s", exc)
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable") from exc

    daily_spent = float(daily_raw or 0.0)
    monthly_spent = float(monthly_raw or 0.0)

    if daily_spent >= settings.daily_budget_usd or monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget limit exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Tính và cộng dồn chi phí request vào bộ đếm ngày/tháng trong Redis.

    Tham số:
        input_tokens: Số token đầu vào đã sử dụng.
        output_tokens: Số token đầu ra đã sinh ra.

    Trả về:
        Chi phí (USD) của request hiện tại.
    """
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )

    if r is None:
        logger.error("cost_guard_backend_missing_on_record")
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable")

    daily_key, monthly_key = _budget_keys()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, DAILY_TTL_SECONDS)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, MONTHLY_TTL_SECONDS)
        pipe.execute()
    except (redis.RedisError, OSError) as exc:
        logger.error("cost_guard_write_error: %s", exc)
        raise HTTPException(status_code=503, detail="Cost guard backend unavailable") from exc

    return round(cost, 8)
