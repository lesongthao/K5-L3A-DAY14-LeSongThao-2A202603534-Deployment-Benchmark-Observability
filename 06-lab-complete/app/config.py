"""Quản lý cấu hình theo chuẩn 12-Factor: đọc toàn bộ thiết lập từ biến môi trường."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Nạp biến môi trường từ tệp .env khi chạy cục bộ (không ghi đè biến đã có sẵn từ shell/Docker)
load_dotenv()


def _env_int(name: str, default: int) -> int:
    """Đọc số nguyên từ biến môi trường, trả về mặc định nếu thiếu hoặc sai định dạng."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """Đọc số thực từ biến môi trường, trả về mặc định nếu thiếu hoặc sai định dạng."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    """Cấu hình tập trung cho Production AI Agent."""

    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))
    monthly_budget_usd: float = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", 10.0))


settings = Settings()
