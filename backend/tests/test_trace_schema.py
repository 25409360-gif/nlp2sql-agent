import unittest
from datetime import datetime
from decimal import Decimal

from pydantic import ValidationError

from app.schemas.trace import (
    REDACTED_VALUE,
    TRACE_STATUSES,
    TraceEvent,
    TraceResponse,
    append_trace_event,
    sanitize_trace_payload,
    trace_events_to_dicts,
)


class TraceSchemaTest(unittest.TestCase):
    def test_trace_event_accepts_defined_statuses(self) -> None:
        for status in TRACE_STATUSES:
            event = TraceEvent(step="intent_analysis", status=status)
            self.assertEqual(event.status, status)
            self.assertEqual(event.input, {})
            self.assertEqual(event.output, {})

    def test_trace_event_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValidationError):
            TraceEvent(step="intent_analysis", status="done")

    def test_append_trace_event_sanitizes_sensitive_data(self) -> None:
        trace = []

        event = append_trace_event(
            trace=trace,
            step="llm_call",
            status="success",
            input_data={
                "question": "谁迟到最多？",
                "llm_api_key": "sk-test",
                "nested": {
                    "Authorization": "Bearer token",
                    "safe": "visible",
                },
            },
            output_data={
                "sql": "SELECT id FROM users",
                "token_usage": {"total": 10},
            },
            message="LLM call completed",
            duration_ms=12.5,
        )

        self.assertEqual(len(trace), 1)
        self.assertIs(trace[0], event)
        self.assertEqual(event.input["question"], "谁迟到最多？")
        self.assertEqual(event.input["llm_api_key"], REDACTED_VALUE)
        self.assertEqual(event.input["nested"]["Authorization"], REDACTED_VALUE)
        self.assertEqual(event.input["nested"]["safe"], "visible")
        self.assertEqual(event.output["token_usage"], REDACTED_VALUE)
        self.assertEqual(event.duration_ms, 12.5)

    def test_sanitize_trace_payload_returns_frontend_safe_values(self) -> None:
        sanitized = sanitize_trace_payload(
            {
                "created_at": datetime(2026, 6, 5, 12, 30, 0),
                "cost": Decimal("12.34"),
                "items": ({"password": "secret", "name": "张三"},),
            }
        )

        self.assertEqual(sanitized["created_at"], "2026-06-05T12:30:00")
        self.assertEqual(sanitized["cost"], 12.34)
        self.assertIsInstance(sanitized["items"], list)
        self.assertEqual(sanitized["items"][0]["password"], REDACTED_VALUE)
        self.assertEqual(sanitized["items"][0]["name"], "张三")

    def test_trace_response_can_render_for_frontend(self) -> None:
        trace = []
        append_trace_event(
            trace=trace,
            step="sql_validation",
            status="success",
            input_data={"sql": "SELECT id FROM users"},
            output_data={"valid": True},
            duration_ms=3,
        )

        response = TraceResponse(events=trace)
        payload = response.model_dump(mode="json")
        event_payloads = trace_events_to_dicts(trace)

        self.assertEqual(payload["events"][0]["step"], "sql_validation")
        self.assertEqual(payload["events"][0]["duration_ms"], 3)
        self.assertEqual(event_payloads[0]["status"], "success")
        self.assertEqual(event_payloads[0]["output"]["valid"], True)


if __name__ == "__main__":
    unittest.main()
