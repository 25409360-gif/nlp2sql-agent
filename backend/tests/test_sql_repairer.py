import unittest

from app.agent.sql_repairer import SQLRepairer
from app.agent.sql_validator import SQLValidator


SCHEMA_CONTEXT = [
    {
        "table_name": "users",
        "columns": ["id", "name", "department_id"],
    },
    {
        "table_name": "departments",
        "columns": ["id", "name"],
    },
    {
        "table_name": "attendance_records",
        "columns": ["id", "user_id", "status"],
    },
]


class FakeResponse:
    def __init__(self, parsed_json=None, content="") -> None:
        self.parsed_json = parsed_json
        self.content = content


class StaticRepairLLM:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = 0

    def chat_completion(self, **kwargs):
        self.calls += 1
        return FakeResponse(parsed_json=self.payload)

    def extract_json(self, content):
        raise AssertionError("extract_json should not be called")


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.last_sql = None

    def execute(self, validation_result):
        self.calls += 1
        self.last_sql = validation_result["safe_sql"]
        return {
            "success": True,
            "sql": validation_result["safe_sql"],
            "columns": ["name"],
            "rows": [{"name": "王子轩"}],
            "row_count": 1,
            "execution_time_ms": 1.2,
            "truncated": False,
            "error": None,
        }


class SQLRepairerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SQLValidator(default_limit=100, max_limit=500)

    def test_repairs_wrong_column_name(self) -> None:
        executor = FakeExecutor()
        repairer = SQLRepairer(
            llm_client=StaticRepairLLM(
                {
                    "status": "repaired",
                    "repaired_sql": "SELECT u.name FROM users u ORDER BY u.id LIMIT 5",
                    "changes": ["Changed users.full_name to users.name."],
                    "tables_used": ["users"],
                    "columns_used": ["users.id", "users.name"],
                    "explanation": "The users table has name, not full_name.",
                }
            ),
            validator=self.validator,
            executor=executor,
            max_attempts=1,
        )

        result = repairer.repair(
            question="列出用户姓名",
            failed_sql="SELECT u.full_name FROM users u LIMIT 5",
            error_message="Unknown column: users.full_name",
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertEqual(result["status"], "repaired")
        self.assertEqual(result["repaired_sql"], "SELECT u.name FROM users u ORDER BY u.id LIMIT 5")
        self.assertTrue(result["validation_result"]["valid"])
        self.assertTrue(result["execution_result"]["success"])
        self.assertEqual(executor.calls, 1)
        self.assertEqual(result["attempts"][0]["status"], "repaired")

    def test_repairs_wrong_table_name(self) -> None:
        executor = FakeExecutor()
        repairer = SQLRepairer(
            llm_client=StaticRepairLLM(
                {
                    "status": "repaired",
                    "repaired_sql": (
                        "SELECT d.name, COUNT(u.id) AS user_count "
                        "FROM departments d "
                        "JOIN users u ON u.department_id = d.id "
                        "GROUP BY d.id, d.name "
                        "ORDER BY user_count DESC "
                        "LIMIT 10"
                    ),
                    "changes": ["Changed department to departments."],
                    "tables_used": ["departments", "users"],
                    "columns_used": ["departments.id", "departments.name", "users.id", "users.department_id"],
                    "explanation": "The schema contains departments, not department.",
                }
            ),
            validator=self.validator,
            executor=executor,
            max_attempts=1,
        )

        result = repairer.repair(
            question="每个部门有多少员工？",
            failed_sql=(
                "SELECT d.name, COUNT(u.id) AS user_count "
                "FROM department d "
                "JOIN users u ON u.department_id = d.id "
                "GROUP BY d.name"
            ),
            error_message="Unknown table(s): department",
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertEqual(result["status"], "repaired")
        self.assertIn("FROM departments d", result["repaired_sql"])
        self.assertTrue(result["validation_result"]["valid"])
        self.assertTrue(result["execution_result"]["success"])
        self.assertEqual(executor.calls, 1)

    def test_rejects_unsafe_repair(self) -> None:
        executor = FakeExecutor()
        repairer = SQLRepairer(
            llm_client=StaticRepairLLM(
                {
                    "status": "repaired",
                    "repaired_sql": "DELETE FROM users",
                    "changes": ["Tried unsafe SQL."],
                    "tables_used": ["users"],
                    "columns_used": [],
                    "explanation": "Unsafe response.",
                }
            ),
            validator=self.validator,
            executor=executor,
            max_attempts=1,
        )

        result = repairer.repair(
            question="删除用户",
            failed_sql="SELECT fake FROM users",
            error_message="Unknown column: fake",
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["repaired_sql"])
        self.assertIn("Only SELECT", result["failure_reason"])
        self.assertEqual(result["attempts"][0]["status"], "validation_failed")
        self.assertEqual(executor.calls, 0)

    def test_returns_unrepairable_response(self) -> None:
        repairer = SQLRepairer(
            llm_client=StaticRepairLLM(
                {
                    "status": "unrepairable",
                    "repaired_sql": None,
                    "changes": [],
                    "tables_used": [],
                    "columns_used": [],
                    "explanation": "The request asks for a destructive operation.",
                }
            ),
            validator=self.validator,
            executor=FakeExecutor(),
            max_attempts=1,
        )

        result = repairer.repair(
            question="把用户删掉",
            failed_sql="DELETE FROM users",
            error_message="Only SELECT statements are allowed",
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertEqual(result["status"], "unrepairable")
        self.assertIsNone(result["repaired_sql"])
        self.assertIn("destructive", result["failure_reason"])


if __name__ == "__main__":
    unittest.main()
