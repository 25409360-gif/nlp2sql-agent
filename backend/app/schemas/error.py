from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class APIErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: APIError
