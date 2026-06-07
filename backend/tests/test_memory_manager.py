import json
import unittest

from app.agent.memory_manager import ConversationMemoryManager


class InMemoryRedisStore:
    def __init__(self) -> None:
        self.values = {}
        self.ttls = {}

    def load_json(self, key):
        value = self.values.get(key)
        if value is None:
            return None
        return json.loads(value)

    def set_value(self, key, value, ttl_seconds=None):
        self.values[key] = value
        self.ttls[key] = ttl_seconds
        return True

    def delete_value(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.ttls.pop(key, None)
        return 1 if existed else 0


class ConversationMemoryManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryRedisStore()
        self.manager = ConversationMemoryManager(
            max_turns=2,
            ttl_seconds=60,
            load_json_func=self.store.load_json,
            set_value_func=self.store.set_value,
            delete_value_func=self.store.delete_value,
        )

    def test_save_and_load_last_n_turns(self) -> None:
        self.manager.save(
            "session-1",
            {
                "question": "第一问",
                "answer": "第一答",
                "sql": "SELECT 1",
                "status": "success",
                "resolved_entities": {"tables": ["users"]},
                "retrieved_tables": ["users"],
                "columns": ["id", "name"],
                "rows": [{"id": 1, "name": "王子轩"}],
                "row_count": 1,
            },
        )
        self.manager.save(
            "session-1",
            {
                "question": "第二问",
                "answer": "第二答",
                "sql": "SELECT 2",
                "status": "success",
            },
        )
        self.manager.save(
            "session-1",
            {
                "question": "第三问",
                "answer": "第三答",
                "sql": "SELECT 3",
                "status": "success",
            },
        )

        turns = self.manager.load("session-1")

        self.assertEqual([turn["question"] for turn in turns], ["第二问", "第三问"])
        self.assertEqual(self.store.ttls["sessions:session-1:history"], 60)

    def test_save_preserves_result_columns_and_rows(self) -> None:
        self.manager.save(
            "session-1",
            {
                "question": "列出用户",
                "answer": "查到 1 个用户。",
                "sql": "SELECT id, name FROM users LIMIT 1",
                "status": "success",
                "columns": ["id", "name"],
                "rows": [{"id": 1, "name": "王子轩"}],
                "row_count": 1,
            },
        )

        turn = self.manager.load("session-1")[0]

        self.assertEqual(turn["columns"], ["id", "name"])
        self.assertEqual(turn["rows"], [{"id": 1, "name": "王子轩"}])

    def test_get_history_with_limit(self) -> None:
        self.manager.save("session-1", {"question": "第一问", "answer": "第一答", "status": "success"})
        self.manager.save("session-1", {"question": "第二问", "answer": "第二答", "status": "success"})

        history = self.manager.get_history("session-1", limit=1)

        self.assertEqual(history["session_id"], "session-1")
        self.assertEqual(history["count"], 1)
        self.assertEqual(history["turns"][0]["question"], "第二问")

    def test_clear_session(self) -> None:
        self.manager.save("session-1", {"question": "问题", "answer": "回答", "status": "success"})

        self.assertTrue(self.manager.clear("session-1"))
        self.assertFalse(self.manager.clear("session-1"))
        self.assertEqual(self.manager.load("session-1"), [])

    def test_rejects_empty_session_id(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.load(" ")


if __name__ == "__main__":
    unittest.main()
