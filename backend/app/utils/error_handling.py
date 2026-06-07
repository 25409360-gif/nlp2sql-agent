import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, sanitize_for_log

logger = get_logger(__name__)


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


ERROR_MESSAGES = {
    "invalid_request": "请求内容不完整或格式不正确。",
    "validation_error": "请求参数不完整或格式不正确。",
    "not_found": "请求的资源不存在。",
    "chat_query_failed": "查询处理失败，请稍后重试。",
    "unsupported_request": "这个问题暂时不支持。我只能处理只读的数据查询。",
    "llm_missing_api_key": "缺少大模型 API Key。请配置 LLM_API_KEY，或临时切换为 mock 模式。",
    "llm_missing_api_base_url": "缺少大模型 API 地址。请配置 LLM_API_BASE_URL。",
    "llm_timeout": "大模型响应超时。请稍后重试，或调高 LLM_TIMEOUT_SECONDS。",
    "llm_invalid_json": "大模型返回格式不符合要求。请重试一次，或检查当前模型是否支持 JSON 输出。",
    "schema_retrieval_failed": "读取数据库结构失败。请确认数据库和检索服务正在运行。",
    "vector_store_unavailable": "向量检索服务暂时不可用。请确认 Chroma 容器正在运行。",
    "sql_generation_failed": "暂时无法生成安全 SQL。请换一种更明确的问法。",
    "sql_validation_failed": "生成的 SQL 没有通过安全校验，系统已阻止执行。",
    "sql_execution_failed": "SQL 执行失败。可能是字段、表结构或数据库连接有问题。",
    "redis_unavailable": "会话记忆暂时不可用。请确认 Redis 正在运行。",
    "database_unavailable": "数据库暂时不可用。请确认 PostgreSQL 正在运行。",
    "internal_error": "服务内部处理失败，请稍后重试。",
    "needs_clarification": "这个问题还不够明确，请补充查询对象、时间范围或筛选条件。",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        payload = normalize_http_exception_detail(exc.detail, exc.status_code)
        logger.warning(
            "api.error status_code=%s path=%s code=%s message=%s",
            exc.status_code,
            request.url.path,
            payload["error"]["code"],
            sanitize_for_log(payload["error"]["message"]),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        error_info = ErrorInfo(
            code="validation_error",
            message=ERROR_MESSAGES["validation_error"],
            details={"errors": sanitize_error_payload(exc.errors())},
        )
        logger.warning(
            "api.validation_error path=%s details=%s",
            request.url.path,
            sanitize_for_log(error_info.details),
        )
        return JSONResponse(status_code=422, content=error_response(error_info))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_info = classify_error(exc, default_code="internal_error")
        logger.error(
            "api.unhandled_error path=%s code=%s error=%s",
            request.url.path,
            error_info.code,
            sanitize_for_log(str(exc)),
        )
        return JSONResponse(status_code=500, content=error_response(error_info))


def http_error(
    status_code: int,
    code: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    error_info = ErrorInfo(
        code=code,
        message=message or ERROR_MESSAGES.get(code, ERROR_MESSAGES["internal_error"]),
        details=sanitize_error_payload(details or {}),
    )
    return HTTPException(status_code=status_code, detail=error_response(error_info))


def error_response(error_info: ErrorInfo) -> dict[str, Any]:
    return {"error": error_info.to_dict()}


def normalize_http_exception_detail(detail: Any, status_code: int) -> dict[str, Any]:
    if isinstance(detail, dict):
        if isinstance(detail.get("error"), dict):
            error = detail["error"]
            return error_response(
                ErrorInfo(
                    code=str(error.get("code") or fallback_code_for_status(status_code)),
                    message=str(error.get("message") or fallback_message_for_status(status_code)),
                    details=sanitize_error_payload(error.get("details") or {}),
                )
            )
        if "code" in detail and "message" in detail:
            return error_response(
                ErrorInfo(
                    code=str(detail["code"]),
                    message=str(detail["message"]),
                    details=sanitize_error_payload(detail.get("details") or {}),
                )
            )

    error_info = classify_error(
        detail,
        default_code=fallback_code_for_status(status_code),
        fallback_message=fallback_message_for_status(status_code),
    )
    return error_response(error_info)


def classify_error(
    error: Any,
    status: str | None = None,
    failed_step: str | None = None,
    default_code: str = "internal_error",
    fallback_message: str | None = None,
) -> ErrorInfo:
    text = sanitize_error_text(str(error or ""))
    lowered = text.lower()
    step = (failed_step or "").lower()
    error_type = type(error).__name__.lower()

    if status == "unsupported" or "unsupported question type" in lowered:
        return _info("unsupported_request", text)
    if "question must not be empty" in lowered or "session_id must not be empty" in lowered:
        return _info("invalid_request", text)
    if "llm_api_key" in lowered or "missingllmapikeyerror" in error_type:
        return _info("llm_missing_api_key", text)
    if "llm_api_base_url" in lowered:
        return _info("llm_missing_api_base_url", text)
    if "timed out" in lowered or "timeout" in lowered or "llmtimeouterror" in error_type:
        return _info("llm_timeout", text)
    if "valid json" in lowered or "invalid json" in lowered or "json object" in lowered:
        return _info("llm_invalid_json", text)
    if "redis" in lowered or "cache" in lowered:
        return _info("redis_unavailable", text)
    if "postgresql connection" in lowered or "databaseconnectionerror" in error_type:
        return _info("database_unavailable", text)
    if step == "schema_retrieval":
        if _looks_like_vector_store_error(lowered):
            return _info("vector_store_unavailable", text)
        return _info("schema_retrieval_failed", text)
    if _looks_like_vector_store_error(lowered):
        return _info("vector_store_unavailable", text)
    if step == "sql_validation" or _looks_like_sql_validation_error(lowered):
        return _info("sql_validation_failed", text)
    if step == "sql_execution" or _looks_like_sql_execution_error(lowered):
        return _info("sql_execution_failed", text)
    if status == "needs_clarification":
        return _info("needs_clarification", text)

    return ErrorInfo(
        code=default_code,
        message=fallback_message or ERROR_MESSAGES.get(default_code, ERROR_MESSAGES["internal_error"]),
        details={"reason": text} if text else {},
    )


def failed_step_from_trace(trace: list[Any]) -> str | None:
    for event in reversed(trace):
        if isinstance(event, dict):
            if event.get("status") == "failed":
                return str(event.get("step") or "") or None
            continue

        if getattr(event, "status", None) == "failed":
            return str(getattr(event, "step", "") or "") or None
    return None


def sanitize_error_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): sanitize_error_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [sanitize_error_payload(item) for item in payload]
    if isinstance(payload, str):
        return sanitize_error_text(payload)
    return payload


def sanitize_error_text(text: str) -> str:
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-[REDACTED]", sanitized)
    return sanitized


def fallback_code_for_status(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 422:
        return "validation_error"
    if 400 <= status_code < 500:
        return "invalid_request"
    return "internal_error"


def fallback_message_for_status(status_code: int) -> str:
    if status_code == 404:
        return ERROR_MESSAGES["not_found"]
    if status_code == 422:
        return ERROR_MESSAGES["validation_error"]
    if 400 <= status_code < 500:
        return ERROR_MESSAGES["invalid_request"]
    return ERROR_MESSAGES["internal_error"]


def _info(code: str, reason: str) -> ErrorInfo:
    details = {"reason": reason} if reason else {}
    return ErrorInfo(code=code, message=ERROR_MESSAGES[code], details=details)


def _looks_like_vector_store_error(lowered: str) -> bool:
    terms = ["vector store", "chroma", "chromadb", "collection", "connection refused", "connecterror"]
    return any(term in lowered for term in terms)


def _looks_like_sql_validation_error(lowered: str) -> bool:
    terms = [
        "sql validation",
        "only select",
        "only one sql statement",
        "unknown table",
        "unknown column",
        "ambiguous unqualified column",
        "sensitive column",
        "parse error",
    ]
    return any(term in lowered for term in terms)


def _looks_like_sql_execution_error(lowered: str) -> bool:
    terms = [
        "sql execution",
        "sqlalchemy",
        "psycopg",
        "does not exist",
        "statement timeout",
        "division by zero",
        "permission denied",
    ]
    return any(term in lowered for term in terms)
