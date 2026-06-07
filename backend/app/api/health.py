from fastapi import APIRouter

from app.core.config import settings
from app.core.redis import RedisConnectionError, check_redis_connection
from app.db.database import DatabaseConnectionError, check_database_connection
from app.utils.error_handling import http_error

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/api/db/health")
def database_health_check() -> dict:
    try:
        value = check_database_connection()
    except DatabaseConnectionError as exc:
        raise http_error(
            status_code=503,
            code="database_unavailable",
            details={"reason": str(exc)},
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
        "result": value,
    }


@router.get("/api/cache/health")
def cache_health_check() -> dict:
    try:
        value = check_redis_connection()
    except RedisConnectionError as exc:
        raise http_error(
            status_code=503,
            code="redis_unavailable",
            details={"reason": str(exc)},
        ) from exc

    return {
        "status": "ok",
        "cache": "connected",
        "result": value,
    }
