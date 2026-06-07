import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


class RedisConnectionError(RuntimeError):
    pass


redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


def build_cache_key(key: str) -> str:
    normalized_key = key.strip().lstrip(":")
    return f"{settings.redis_key_prefix}:{normalized_key}"


def check_redis_connection() -> bool:
    try:
        return bool(redis_client.ping())
    except RedisError as exc:
        raise RedisConnectionError("Redis connection failed") from exc


def get_value(key: str) -> str | None:
    try:
        return redis_client.get(build_cache_key(key))
    except RedisError as exc:
        raise RedisConnectionError("Redis get failed") from exc


def set_value(key: str, value: str, ttl_seconds: int | None = None) -> bool:
    ttl = ttl_seconds if ttl_seconds is not None else settings.redis_default_ttl_seconds
    try:
        return bool(redis_client.set(build_cache_key(key), value, ex=ttl))
    except RedisError as exc:
        raise RedisConnectionError("Redis set failed") from exc


def delete_value(key: str) -> int:
    try:
        return int(redis_client.delete(build_cache_key(key)))
    except RedisError as exc:
        raise RedisConnectionError("Redis delete failed") from exc


def load_json(key: str) -> Any | None:
    raw_value = get_value(key)
    if raw_value is None:
        return None
    return json.loads(raw_value)


def append_json(key: str, item: Any, ttl_seconds: int | None = None) -> list[Any]:
    current_value = load_json(key)
    if current_value is None:
        current_items: list[Any] = []
    elif isinstance(current_value, list):
        current_items = current_value
    else:
        raise ValueError("Redis JSON value is not a list")

    current_items.append(item)
    set_value(key, json.dumps(current_items, ensure_ascii=False), ttl_seconds=ttl_seconds)
    return current_items
