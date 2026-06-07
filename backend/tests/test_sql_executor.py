import unittest

from app.agent.sql_executor import SQLExecutor
from app.agent.sql_validator import SQLValidator


class SQLExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SQLValidator(default_limit=100, max_limit=500)
        self.executor = SQLExecutor(max_rows=2)

    def test_executes_validated_sql(self) -> None:
        validation = self.validator.validate(
            "SELECT u.id, u.name FROM users u ORDER BY u.id LIMIT 2",
        )
        result = self.executor.execute(validation)

        self.assertTrue(result["success"])
        self.assertEqual(result["columns"], ["id", "name"])
        self.assertLessEqual(result["row_count"], 2)
        self.assertIsNone(result["error"])
        self.assertGreaterEqual(result["execution_time_ms"], 0)

    def test_rejects_unvalidated_sql(self) -> None:
        result = self.executor.execute(
            {
                "valid": False,
                "safe_sql": None,
                "error": "not validated",
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "not validated")

    def test_captures_database_error(self) -> None:
        result = self.executor.execute(
            {
                "valid": True,
                "safe_sql": "SELECT missing_column FROM users LIMIT 1",
            }
        )

        self.assertFalse(result["success"])
        self.assertIn("missing_column", result["error"])

    def test_truncates_rows_at_executor_limit(self) -> None:
        validation = self.validator.validate(
            "SELECT u.id FROM users u ORDER BY u.id LIMIT 5",
        )
        result = self.executor.execute(validation)

        self.assertTrue(result["success"])
        self.assertLessEqual(result["row_count"], 2)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
