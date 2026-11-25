"""Kết nối Redis dùng chung cho Rate Limiter, Cost Guard và kiểm tra Readiness."""
import redis

from app.config import settings


def _create_redis_client() -> redis.Redis | None:
    """Khởi tạo Redis client không chặn lúc import để app vẫn khởi động khi Redis chưa sẵn sàng."""
    if not settings.redis_url:
        return None
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


r: redis.Redis | None = _create_redis_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis bằng lệnh PING cho endpoint GET /ready.

    Trả về:
        True nếu Redis phản hồi PONG, ngược lại False.
    """
    if r is None:
        return False
    try:
        return bool(r.ping())
    except (redis.RedisError, OSError):
        return False


def close_redis() -> None:
    """Đóng connection pool Redis an toàn khi ứng dụng tắt."""
    if r is not None:
        try:
            r.close()
        except (redis.RedisError, OSError):
            pass
