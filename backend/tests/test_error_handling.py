import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils.error_handling import classify_error, http_error, register_error_handlers


class ErrorHandlingTest(unittest.TestCase):
    def test_classifies_common_llm_errors(self) -> None:
        self.assertEqual(classify_error("LLM_API_KEY is required").code, "llm_missing_api_key")
        self.assertEqual(classify_error("LLM request timed out").code, "llm_timeout")
        self.assertEqual(classify_error("LLM response does not contain valid JSON").code, "llm_invalid_json")

    def test_classifies_pipeline_step_failures(self) -> None:
        self.assertEqual(
            classify_error("connection refused", failed_step="schema_retrieval").code,
            "vector_store_unavailable",
        )
        self.assertEqual(
            classify_error("Unknown column: users.full_name", failed_step="sql_validation").code,
            "sql_validation_failed",
        )
        self.assertEqual(
            classify_error("column users.full_name does not exist", failed_step="sql_execution").code,
            "sql_execution_failed",
        )
        self.assertEqual(
            classify_error("redis connection failed", failed_step="memory_load").code,
            "redis_unavailable",
        )

    def test_http_errors_use_standard_response_shape(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/boom")
        def boom():
            raise http_error(
                status_code=503,
                code="redis_unavailable",
                details={"reason": "redis connection failed"},
            )

        response = TestClient(app).get("/boom")

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(set(payload.keys()), {"error"})
        self.assertEqual(payload["error"]["code"], "redis_unavailable")
        self.assertIn("Redis", payload["error"]["message"])
        self.assertEqual(payload["error"]["details"]["reason"], "redis connection failed")

    def test_validation_errors_use_standard_response_shape(self) -> None:
        app = FastAPI()
        register_error_handlers(app)

        @app.get("/items/{item_id}")
        def get_item(item_id: int):
            return {"item_id": item_id}

        response = TestClient(app).get("/items/not-an-int")

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("格式", payload["error"]["message"])
        self.assertTrue(payload["error"]["details"]["errors"])


if __name__ == "__main__":
    unittest.main()
