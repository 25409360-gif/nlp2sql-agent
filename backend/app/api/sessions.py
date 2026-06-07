from fastapi import APIRouter, Depends, Query

from app.agent.memory_manager import ConversationMemoryManager
from app.agent.sql_executor import SQLExecutor
from app.agent.sql_validator import SQLValidator
from app.schemas.session import ClearSessionResponse, SessionHistoryResponse
from app.utils.error_handling import classify_error, http_error


router = APIRouter(prefix="/sessions", tags=["sessions"])


class HistoryResultHydrator:
    def __init__(
        self,
        sql_validator: SQLValidator | None = None,
        sql_executor: SQLExecutor | None = None,
    ) -> None:
        self.sql_validator = sql_validator or SQLValidator()
        self.sql_executor = sql_executor or SQLExecutor()

    def hydrate(self, history: dict) -> dict:
        for turn in history.get("turns") or []:
            if isinstance(turn, dict):
                self._hydrate_turn(turn)
        return history

    def _hydrate_turn(self, turn: dict) -> None:
        if turn.get("columns") or turn.get("rows"):
            return
        if turn.get("status") != "success" or not turn.get("sql"):
            return

        try:
            validation_result = self.sql_validator.validate(str(turn["sql"]))
            if not validation_result.get("valid"):
                return
            execution_result = self.sql_executor.execute(validation_result)
            if not execution_result.get("success"):
                return
        except Exception:
            return

        turn["columns"] = execution_result.get("columns") or []
        turn["rows"] = execution_result.get("rows") or []
        turn["row_count"] = int(execution_result.get("row_count") or turn.get("row_count") or 0)


def create_memory_manager() -> ConversationMemoryManager:
    return ConversationMemoryManager()


def create_history_result_hydrator() -> HistoryResultHydrator:
    return HistoryResultHydrator()


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(
    session_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    memory_manager: ConversationMemoryManager = Depends(create_memory_manager),
    history_result_hydrator: HistoryResultHydrator = Depends(create_history_result_hydrator),
) -> SessionHistoryResponse:
    try:
        history = history_result_hydrator.hydrate(memory_manager.get_history(session_id, limit=limit))
    except ValueError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, failed_step="memory_load")
        raise http_error(
            status_code=503,
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return SessionHistoryResponse(**history)


@router.delete("/{session_id}", response_model=ClearSessionResponse)
def clear_session(
    session_id: str,
    memory_manager: ConversationMemoryManager = Depends(create_memory_manager),
) -> ClearSessionResponse:
    try:
        cleared = memory_manager.clear(session_id)
    except ValueError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, failed_step="memory_save")
        raise http_error(
            status_code=503,
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return ClearSessionResponse(session_id=session_id, cleared=cleared)
