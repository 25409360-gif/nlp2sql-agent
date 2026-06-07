import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import create_text2sql_agent, router
from app.utils.error_handling import register_error_handlers


class FakeText2SQLAgent:
    def __init__(self) -> None:
        self.calls = []

    def run(self, question, session_id, selected_table_name=None):
        self.calls.append(
            {
                "question": question,
                "session_id": session_id,
                "selected_table_name": selected_table_name,
            }
        )
        return {
            "status": "success",
            "answer": "查到 1 条记录。",
            "session_id": session_id,
            "sql": "SELECT id FROM users LIMIT 1",
            "columns": ["id"],
            "rows": [{"id": 1}],
            "row_count": 1,
            "trace": [{"step": "intent_analysis", "status": "success"}],
            "retrieved_schema": [{"table_name": "users", "columns": ["id"]}],
            "error": None,
        }


class FailingText2SQLAgent:
    def run(self, question, session_id, selected_table_name=None):
        raise RuntimeError("agent crashed")


class ChatAPITest(unittest.TestCase):
    def create_client(self, agent):
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[create_text2sql_agent] = lambda: agent
        return TestClient(app)

    def test_chat_endpoint_returns_agent_result(self) -> None:
        agent = FakeText2SQLAgent()
        client = self.create_client(agent)

        response = client.post(
            "/api/chat",
            json={
                "question": "列出用户",
                "session_id": "session-1",
                "selected_table_name": "users",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["answer"], "查到 1 条记录。")
        self.assertEqual(payload["sql"], "SELECT id FROM users LIMIT 1")
        self.assertEqual(payload["columns"], ["id"])
        self.assertEqual(payload["rows"], [{"id": 1}])
        self.assertEqual(payload["trace"][0]["step"], "intent_analysis")
        self.assertEqual(payload["retrieved_schema"][0]["table_name"], "users")
        self.assertIsNone(payload["error"])
        self.assertEqual(agent.calls[0]["selected_table_name"], "users")

    def test_chat_endpoint_validates_request_body(self) -> None:
        client = self.create_client(FakeText2SQLAgent())

        response = client.post(
            "/api/chat",
            json={"question": "", "session_id": "session-1"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_chat_endpoint_returns_500_when_agent_crashes(self) -> None:
        client = self.create_client(FailingText2SQLAgent())

        response = client.post(
            "/api/chat",
            json={"question": "列出用户", "session_id": "session-1"},
        )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "chat_query_failed")
        self.assertIn("查询处理失败", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
