from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TraceStatus = Literal["pending", "running", "success", "failed", "skipped"]

TRACE_STATUSES: tuple[str, ...] = ("pending", "running", "success", "failed", "skipped")
REDACTED_VALUE = "[REDACTED]"
SENSITIVE_KEYWORDS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str = Field(min_length=1)
    status: TraceStatus
    input: Any = Field(default_factory=dict)
    output: Any = Field(default_factory=dict)
    message: str = ""
    duration_ms: float | None = Field(default=None, ge=0)


class TraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[TraceEvent] = Field(default_factory=list)


def append_trace_event(
    trace: list[TraceEvent | dict[str, Any]],
    step: str,
    status: TraceStatus,
    input_data: Any | None = None,
    output_data: Any | None = None,
    message: str = "",
    duration_ms: float | None = None,
) -> TraceEvent:
    event = TraceEvent(
        step=step,
        status=status,
        input=sanitize_trace_payload(input_data if input_data is not None else {}),
        output=sanitize_trace_payload(output_data if output_data is not None else {}),
        message=message,
        duration_ms=duration_ms,
    )
    trace.append(event)
    return event


def sanitize_trace_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): REDACTED_VALUE if _is_sensitive_key(key) else sanitize_trace_payload(value)
            for key, value in payload.items()
        }

    if isinstance(payload, (list, tuple, set)):
        return [sanitize_trace_payload(item) for item in payload]

    if payload is None or isinstance(payload, (str, int, float, bool)):
        return payload

    if isinstance(payload, Decimal):
        return float(payload)

    if isinstance(payload, (datetime, date, time)):
        return payload.isoformat()

    return str(payload)


def trace_events_to_dicts(trace: list[TraceEvent | dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for event in trace:
        if isinstance(event, TraceEvent):
            events.append(event.model_dump(mode="json"))
            continue

        normalized = TraceEvent(
            step=str(event.get("step") or ""),
            status=event.get("status"),
            input=sanitize_trace_payload(event.get("input", {})),
            output=sanitize_trace_payload(event.get("output", {})),
            message=str(event.get("message") or ""),
            duration_ms=event.get("duration_ms"),
        )
        events.append(normalized.model_dump(mode="json"))
    return events


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(keyword in normalized for keyword in SENSITIVE_KEYWORDS)
