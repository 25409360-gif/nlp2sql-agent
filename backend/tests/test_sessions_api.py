import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sessions import create_history_result_hydrator, create_memory_manager, router
from app.utils.error_handling import register_error_handlers


class FakeMemoryManager:
    def __init__(self, turns=None) -> None:
        self.cleared = []
        self.turns = turns or [
            {
                "question": "谁迟到最多？",
                "answer": "郭亦辰迟到次数最多。",
                "sql": "SELECT 1",
                "status": "success",
                "error": None,
                "summary": {"answer": "郭亦辰迟到次数最多。"},
                "resolved_entities": {"tables": ["attendance_records", "users"]},
                "retrieved_tables": ["attendance_records", "users"],
                "columns": ["name", "late_count"],
                "rows": [{"name": "郭亦辰", "late_count": 15}],
                "row_count": 1,
                "created_at": "2026-06-05T00:00:00+00:00",
            }
        ]

    def get_history(self, session_id, limit=10):
        return {
            "session_id": session_id,
            "turns": self.turns[:limit],
            "count": len(self.turns[:limit]),
        }

    def clear(self, session_id):
        self.cleared.append(session_id)
        return True


class FakeHistoryResultHydrator:
    def __init__(self) -> None:
        self.calls = 0

    def hydrate(self, history):
        self.calls += 1
        for turn in history.get("turns", []):
            if not turn.get("columns"):
                turn["columns"] = ["id", "name"]
                turn["rows"] = [{"id": 5, "name": "测试组"}]
        return history


class SessionsAPITest(unittest.TestCase):
    def create_client(self, memory_manager, history_result_hydrator=None):
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[create_memory_manager] = lambda: memory_manager
        if history_result_hydrator is not None:
            app.dependency_overrides[create_history_result_hydrator] = lambda: history_result_hydrator
        return TestClient(app)

    def test_get_session_history(self) -> None:
        client = self.create_client(FakeMemoryManager())

        response = client.get("/api/sessions/session-1/history?limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["session_id"], "session-1")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["turns"][0]["question"], "谁迟到最多？")
        self.assertEqual(payload["turns"][0]["retrieved_tables"], ["attendance_records", "users"])
        self.assertEqual(payload["turns"][0]["columns"], ["name", "late_count"])
        self.assertEqual(payload["turns"][0]["rows"], [{"name": "郭亦辰", "late_count": 15}])

    def test_get_session_history_hydrates_legacy_result_rows(self) -> None:
        legacy_turn = {
            "question": "负责质量保障的是哪个部门",
            "answer": "负责质量保障的部门是测试组。",
            "sql": "SELECT d.id, d.name FROM departments d LIMIT 1",
            "status": "success",
            "error": None,
            "summary": {},
            "resolved_entities": {"tables": ["departments"]},
            "retrieved_tables": ["departments"],
            "row_count": 1,
            "created_at": "2026-06-05T00:00:00+00:00",
        }
        hydrator = FakeHistoryResultHydrator()
        client = self.create_client(FakeMemoryManager(turns=[legacy_turn]), history_result_hydrator=hydrator)

        response = client.get("/api/sessions/session-1/history?limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["turns"][0]["columns"], ["id", "name"])
        self.assertEqual(payload["turns"][0]["rows"], [{"id": 5, "name": "测试组"}])
        self.assertEqual(hydrator.calls, 1)

    def test_clear_session(self) -> None:
        memory_manager = FakeMemoryManager()
        client = self.create_client(memory_manager)

        response = client.delete("/api/sessions/session-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"session_id": "session-1", "cleared": True})
        self.assertEqual(memory_manager.cleared, ["session-1"])

    def test_history_limit_validation(self) -> None:
        client = self.create_client(FakeMemoryManager())

        response = client.get("/api/sessions/session-1/history?limit=0")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
