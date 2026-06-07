from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    selected_table_name: str | None = Field(default=None, min_length=1)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    answer: str
    session_id: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    trace: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_schema: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
