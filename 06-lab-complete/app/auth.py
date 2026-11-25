"""Xác thực API Key qua header X-API-Key (tiêu chí 6)."""
import secrets

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

# Đặt auto_error=False để chủ động trả về HTTP 401 thay vì 403 mặc định của FastAPI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Kiểm tra header X-API-Key khớp với biến môi trường AGENT_API_KEY.

    Tham số:
        api_key: Giá trị header X-API-Key trích xuất từ request.

    Trả về:
        Chuỗi API key hợp lệ để dùng làm khóa định danh cho rate limiter.

    Ngoại lệ:
        HTTPException(401): Khi chưa cấu hình AGENT_API_KEY hoặc key thiếu/sai.
    """
    expected_key = settings.agent_api_key
    if not expected_key or not api_key or not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key",
        )
    return api_key
