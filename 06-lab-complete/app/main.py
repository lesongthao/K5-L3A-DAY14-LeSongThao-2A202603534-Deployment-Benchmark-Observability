"""Production AI Agent — Part 6 Final Project hoàn chỉnh đạt 12/12 tiêu chí."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mọi bản ghi log của ứng dụng thành một dòng JSON hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        """Chuyển đổi LogRecord thành chuỗi JSON chuẩn.

        Tham số:
            record: Bản ghi log từ thư viện logging chuẩn.

        Trả về:
            Chuỗi JSON một dòng chứa thời gian, mức log, thông điệp và metadata.
        """
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _setup_json_logger() -> logging.Logger:
    """Khởi tạo logger riêng cho app xuất JSON ra stdout, không đè log uvicorn."""
    app_logger = logging.getLogger("agent_app")
    app_logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    app_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app_logger.addHandler(handler)
    app_logger.propagate = False
    return app_logger


logger = _setup_json_logger()
START_TIME = time.time()


def _log_json(level: int, event: str, **fields: Any) -> None:
    """Ghi một sự kiện dạng JSON kèm các trường dữ liệu bổ sung."""
    logger.log(level, event, extra={"extra_fields": {"event": event, **fields}})


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Quản lý vòng đời khởi động và tắt êm (graceful shutdown) của FastAPI.

    Khi nhận SIGTERM, uvicorn ngừng nhận kết nối mới, chờ request đang xử lý
    hoàn tất rồi mới chạy nhánh dọn dẹp sau `yield` trước khi thoát với exit code 0.
    """
    _log_json(
        logging.INFO,
        "startup",
        environment=settings.environment,
        port=settings.port,
    )
    yield
    _log_json(logging.INFO, "graceful_shutdown", status="closing_resources")
    close_redis()
    _log_json(logging.INFO, "graceful_shutdown_complete")


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Ghi log JSON cho từng HTTP request kèm phương thức, đường dẫn, mã trạng thái và độ trễ."""
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _log_json(
            logging.INFO,
            "http_request",
            method=request.method,
            path=request.url.path,
            status=status_code,
            ms=elapsed_ms,
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Trả về lỗi 422 gọn gàng, dễ đọc khi dữ liệu đầu vào sai định dạng."""
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request payload", "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Chặn lộ stack trace nội bộ khi có lỗi không mong muốn phát sinh."""
    _log_json(logging.ERROR, "unhandled_error", error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


class AskRequest(BaseModel):
    """Mô hình dữ liệu đầu vào cho endpoint POST /ask."""

    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe: luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Readiness probe: trả 200 khi Redis sẵn sàng, trả 503 khi mất kết nối Redis."""
    if not redis_healthy():
        _log_json(logging.WARNING, "readiness_failed", dependency="redis")
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"ready": True, "redis": "ok"}


@app.post("/ask")
def ask(
    body: AskRequest,
    api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Xử lý câu hỏi qua chuỗi bảo vệ: X-API-Key -> Rate Limit -> Cost Guard -> LLM."""
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    cost_usd = record_cost(input_tokens, output_tokens)

    _log_json(
        logging.INFO,
        "ask_completed",
        user_id=body.user_id or "anonymous",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )

    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        },
    }
