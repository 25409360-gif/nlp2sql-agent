from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import settings
from app.core.redis import delete_value, load_json, set_value


class ConversationMemoryManager:
    def __init__(
        self,
        max_turns: int = 10,
        ttl_seconds: int | None = None,
        key_prefix: str = "sessions",
        load_json_func: Callable[[str], Any | None] = load_json,
        set_value_func: Callable[[str, str, int | None], bool] = set_value,
        delete_value_func: Callable[[str], int] = delete_value,
    ) -> None:
        if max_turns <= 0:
            raise ValueError("max_turns must be greater than 0")

        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else settings.redis_default_ttl_seconds
        self.key_prefix = key_prefix.strip(":") or "sessions"
        self.load_json_func = load_json_func
        self.set_value_func = set_value_func
        self.delete_value_func = delete_value_func

    def load(self, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        session_key = self._session_key(session_id)
        turns = self._load_all(session_key)
        visible_limit = self._normalize_limit(limit)
        return turns[-visible_limit:]

    def save(self, session_id: str, record: dict[str, Any]) -> list[dict[str, Any]]:
        session_key = self._session_key(session_id)
        turns = self._load_all(session_key)
        turns.append(self._normalize_record(record))
        turns = turns[-self.max_turns :]
        self.set_value_func(session_key, self._to_json(turns), self.ttl_seconds)
        return turns

    def get_history(self, session_id: str, limit: int | None = None) -> dict[str, Any]:
        turns = self.load(session_id, limit=limit)
        return {
            "session_id": session_id,
            "turns": turns,
            "count": len(turns),
        }

    def clear(self, session_id: str) -> bool:
        session_key = self._session_key(session_id)
        return self.delete_value_func(session_key) > 0

    def _load_all(self, session_key: str) -> list[dict[str, Any]]:
        value = self.load_json_func(session_key)
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("conversation memory value must be a list")
        return [item for item in value if isinstance(item, dict)]

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": str(record.get("question") or ""),
            "answer": str(record.get("answer") or ""),
            "sql": record.get("sql"),
            "status": str(record.get("status") or ""),
            "error": record.get("error"),
            "summary": record.get("summary"),
            "resolved_entities": record.get("resolved_entities") or {},
            "retrieved_tables": record.get("retrieved_tables") or [],
            "columns": self._string_list(record.get("columns")),
            "rows": self._row_list(record.get("rows")),
            "row_count": int(record.get("row_count") or 0),
            "created_at": record.get("created_at") or datetime.now(timezone.utc).isoformat(),
        }

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]

    def _row_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _normalize_limit(self, limit: int | None) -> int:
        if limit is None:
            return self.max_turns
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        return min(limit, self.max_turns)

    def _session_key(self, session_id: str) -> str:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("session_id must not be empty")
        return f"{self.key_prefix}:{normalized_session_id}:history"

    def _to_json(self, value: Any) -> str:
        import json

        return json.dumps(value, ensure_ascii=False)
