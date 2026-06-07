import unittest

from app.agent.sql_validator import SQLValidator


SCHEMA_CONTEXT = [
    {
        "table_name": "attendance_records",
        "columns": ["id", "user_id", "status", "work_date"],
    },
    {
        "table_name": "users",
        "columns": ["id", "name", "department_id"],
    },
    {
        "table_name": "secrets",
        "columns": ["id", "api_key"],
    },
    {
        "table_name": "departments",
        "columns": ["id", "name", "description"],
    },
]


class SQLValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SQLValidator(default_limit=100, max_limit=500)

    def test_valid_join_sql(self) -> None:
        result = self.validator.validate(
            "SELECT u.name, COUNT(*) AS late_count "
            "FROM attendance_records ar "
            "JOIN users u ON ar.user_id = u.id "
            "WHERE ar.status = 'late' "
            "GROUP BY u.id, u.name "
            "ORDER BY late_count DESC "
            "LIMIT 1",
            SCHEMA_CONTEXT,
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["limit_applied"], 1)
        self.assertEqual(result["referenced_tables"], ["attendance_records", "users"])
        self.assertIn("users.name", result["referenced_columns"])

    def test_default_limit_is_added(self) -> None:
        result = self.validator.validate(
            "SELECT ar.status FROM attendance_records ar",
            SCHEMA_CONTEXT,
        )

        self.assertTrue(result["valid"])
        self.assertTrue(result["safe_sql"].endswith("LIMIT 100"))
        self.assertEqual(result["limit_applied"], 100)

    def test_large_limit_is_capped(self) -> None:
        result = self.validator.validate(
            "SELECT ar.status FROM attendance_records ar LIMIT 9999",
            SCHEMA_CONTEXT,
        )

        self.assertTrue(result["valid"])
        self.assertTrue(result["safe_sql"].endswith("LIMIT 500"))
        self.assertEqual(result["limit_applied"], 500)

    def test_rejects_mutation_sql(self) -> None:
        result = self.validator.validate(
            "DELETE FROM attendance_records WHERE status = 'late'",
            SCHEMA_CONTEXT,
        )

        self.assertFalse(result["valid"])
        self.assertIn("Only SELECT", result["error"])

    def test_rejects_multiple_statements(self) -> None:
        result = self.validator.validate(
            "SELECT ar.status FROM attendance_records ar; SELECT u.name FROM users u",
            SCHEMA_CONTEXT,
        )

        self.assertFalse(result["valid"])
        self.assertIn("Only one SQL statement", result["error"])

    def test_rejects_unknown_table(self) -> None:
        result = self.validator.validate(
            "SELECT e.id FROM equipment_usage e LIMIT 5",
            SCHEMA_CONTEXT,
        )

        self.assertFalse(result["valid"])
        self.assertIn("Unknown table", result["error"])

    def test_rejects_unknown_column(self) -> None:
        result = self.validator.validate(
            "SELECT ar.fake_column FROM attendance_records ar LIMIT 5",
            SCHEMA_CONTEXT,
        )

        self.assertFalse(result["valid"])
        self.assertIn("Unknown column", result["error"])

    def test_rejects_sensitive_column(self) -> None:
        result = self.validator.validate(
            "SELECT s.api_key FROM secrets s LIMIT 5",
            SCHEMA_CONTEXT,
        )

        self.assertFalse(result["valid"])
        self.assertIn("Sensitive column", result["error"])

    def test_accepts_text_match_sql_with_ilike_escape(self) -> None:
        result = self.validator.validate(
            "SELECT d.id, d.name, d.description, "
            "((CASE WHEN CAST(d.name AS TEXT) ILIKE '%前端%' ESCAPE '!' "
            "OR CAST(d.description AS TEXT) ILIKE '%前端%' ESCAPE '!' THEN 1 ELSE 0 END) + "
            "(CASE WHEN CAST(d.name AS TEXT) ILIKE '%研发%' ESCAPE '!' "
            "OR CAST(d.description AS TEXT) ILIKE '%研发%' ESCAPE '!' THEN 1 ELSE 0 END)) AS match_score "
            "FROM departments d "
            "WHERE ((CASE WHEN CAST(d.name AS TEXT) ILIKE '%前端%' ESCAPE '!' "
            "OR CAST(d.description AS TEXT) ILIKE '%前端%' ESCAPE '!' THEN 1 ELSE 0 END) + "
            "(CASE WHEN CAST(d.name AS TEXT) ILIKE '%研发%' ESCAPE '!' "
            "OR CAST(d.description AS TEXT) ILIKE '%研发%' ESCAPE '!' THEN 1 ELSE 0 END)) >= 2 "
            "ORDER BY match_score DESC, d.id ASC LIMIT 20",
            SCHEMA_CONTEXT,
        )

        self.assertTrue(result["valid"], result["error"])
        self.assertEqual(result["referenced_tables"], ["departments"])
        self.assertIn("departments.description", result["referenced_columns"])


if __name__ == "__main__":
    unittest.main()
