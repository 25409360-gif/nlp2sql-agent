from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionTurn(BaseModel):
    model_config = ConfigDict(extra="allow")

    question: str
    answer: str
    sql: str | None = None
    status: str
    error: str | None = None
    summary: dict[str, Any] | None = None
    resolved_entities: dict[str, Any] = Field(default_factory=dict)
    retrieved_tables: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    created_at: str


class SessionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    turns: list[SessionTurn] = Field(default_factory=list)
    count: int = 0


class ClearSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    cleared: bool
