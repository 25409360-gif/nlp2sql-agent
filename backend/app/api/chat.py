from fastapi import APIRouter, Depends

from app.agent.memory_manager import ConversationMemoryManager
from app.agent.text2sql_agent import Text2SQLAgent
from app.schemas.chat import ChatRequest, ChatResponse
from app.utils.error_handling import classify_error, http_error


router = APIRouter(prefix="/chat", tags=["chat"])


def create_text2sql_agent() -> Text2SQLAgent:
    return Text2SQLAgent(memory_manager=ConversationMemoryManager())


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, agent: Text2SQLAgent = Depends(create_text2sql_agent)) -> ChatResponse:
    try:
        result = agent.run(
            question=request.question,
            session_id=request.session_id,
            selected_table_name=request.selected_table_name,
        )
    except ValueError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, default_code="chat_query_failed")
        raise http_error(
            status_code=500,
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return ChatResponse(
        status=result["status"],
        answer=result["answer"],
        session_id=result["session_id"],
        sql=result.get("sql"),
        columns=result.get("columns") or [],
        rows=result.get("rows") or [],
        row_count=int(result.get("row_count") or 0),
        trace=result.get("trace") or [],
        retrieved_schema=result.get("retrieved_schema") or [],
        error=result.get("error"),
        error_code=result.get("error_code"),
    )
