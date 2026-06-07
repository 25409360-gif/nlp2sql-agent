import logging
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    REDACTED_LOG_VALUE,
    REQUEST_ID_HEADER,
    RequestIdFilter,
    RequestLoggingMiddleware,
    get_request_id,
    reset_request_id,
    sanitize_for_log,
    sanitize_log_text,
    set_request_id,
)


class LoggingTest(unittest.TestCase):
    def test_request_id_filter_adds_context_value(self) -> None:
        token = set_request_id("req-test")
        try:
            record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
            RequestIdFilter().filter(record)
        finally:
            reset_request_id(token)

        self.assertEqual(record.request_id, "req-test")
        self.assertEqual(get_request_id(), "-")

    def test_request_logging_middleware_sets_response_header(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/ok")
        def ok():
            return {"ok": True}

        response = TestClient(app).get("/ok", headers={REQUEST_ID_HEADER: "manual-request-id"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers[REQUEST_ID_HEADER], "manual-request-id")

    def test_sanitize_for_log_redacts_sensitive_values(self) -> None:
        payload = {
            "question": "列出用户",
            "api_key": "sk-secret123456",
            "nested": {"Authorization": "Bearer token-value"},
            "items": [{"password": "plain"}],
        }

        sanitized = sanitize_for_log(payload)

        self.assertEqual(sanitized["question"], "列出用户")
        self.assertEqual(sanitized["api_key"], REDACTED_LOG_VALUE)
        self.assertEqual(sanitized["nested"]["Authorization"], REDACTED_LOG_VALUE)
        self.assertEqual(sanitized["items"][0]["password"], REDACTED_LOG_VALUE)

    def test_sanitize_log_text_redacts_token_like_strings(self) -> None:
        sanitized = sanitize_log_text("Authorization: Bearer abc.def and key sk-1234567890abcdef")

        self.assertIn("Bearer [REDACTED]", sanitized)
        self.assertIn("sk-[REDACTED]", sanitized)
        self.assertNotIn("abc.def", sanitized)
        self.assertNotIn("1234567890abcdef", sanitized)


if __name__ == "__main__":
    unittest.main()
