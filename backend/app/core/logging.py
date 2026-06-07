import contextvars
import logging
import os
import re
import sys
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


REQUEST_ID_HEADER = "X-Request-ID"
REDACTED_LOG_VALUE = "[REDACTED]"
request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "token",
    "secret",
    "password",
    "credential",
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        logger = get_logger("app.request")

        logger.info(
            "request.start method=%s path=%s",
            request.method,
            request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
            logger.error(
                "request.error method=%s path=%s duration_ms=%s error=%s",
                request.method,
                request.url.path,
                duration_ms,
                sanitize_for_log(str(exc)),
            )
            reset_request_id(token)
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request.end method=%s path=%s status_code=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        reset_request_id(token)
        return response


def configure_logging(level: str | None = None) -> None:
    log_level = normalize_log_level(level or os.getenv("LOG_LEVEL", "INFO"))
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    if not any(getattr(handler, "_nlp2sql_configured", False) for handler in root_logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler._nlp2sql_configured = True  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [request_id=%(request_id)s] %(name)s - %(message)s"
            )
        )
        handler.addFilter(RequestIdFilter())
        root_logger.addHandler(handler)

    for handler in root_logger.handlers:
        if getattr(handler, "_nlp2sql_configured", False):
            handler.setLevel(log_level)
            if not any(isinstance(item, RequestIdFilter) for item in handler.filters):
                handler.addFilter(RequestIdFilter())


def normalize_log_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_request_id() -> str:
    return request_id_context.get()


def set_request_id(request_id: str):
    return request_id_context.set(request_id)


def reset_request_id(token) -> None:
    request_id_context.reset(token)


def sanitize_for_log(value: Any, max_depth: int = 4, max_items: int = 20, max_string: int = 500) -> Any:
    if max_depth < 0:
        return "..."

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                sanitized["..."] = f"{len(value) - max_items} more item(s)"
                break
            key_text = str(key)
            if is_sensitive_key(key_text):
                sanitized[key_text] = REDACTED_LOG_VALUE
            else:
                sanitized[key_text] = sanitize_for_log(item, max_depth - 1, max_items, max_string)
        return sanitized

    if isinstance(value, (list, tuple, set)):
        sequence = list(value)
        items = [sanitize_for_log(item, max_depth - 1, max_items, max_string) for item in sequence[:max_items]]
        if len(sequence) > max_items:
            items.append(f"... {len(sequence) - max_items} more item(s)")
        return items

    if isinstance(value, str):
        return truncate_text(sanitize_log_text(value), max_string)

    return value


def sanitize_log_text(text: str) -> str:
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-[REDACTED]", sanitized)
    return sanitized


def truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)
