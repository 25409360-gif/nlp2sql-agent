import json
from typing import Any


SYSTEM_PROMPT = """You are the SQL repair component of an NLP2SQL agent.
Repair invalid SQL using only the provided error details and schema context.
Return exactly one JSON object and no markdown.

Rules:
1. Use PostgreSQL dialect only.
2. The repaired SQL must be read-only SELECT SQL.
3. Never introduce INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, COPY, CALL, EXECUTE, or transaction-control statements.
4. Do not invent tables or columns.
5. Preserve the user's original analytical intent.
6. If the SQL cannot be repaired safely, return status = "unrepairable" with repaired_sql = null."""


EXPECTED_OUTPUT = {
    "status": "repaired | unrepairable",
    "repaired_sql": "string or null",
    "changes": [],
    "tables_used": [],
    "columns_used": [],
    "explanation": "short explanation",
    "safety_checks": {
        "postgresql_dialect": True,
        "read_only": True,
        "uses_only_provided_schema": True,
        "no_invented_tables_or_columns": True,
    },
}


EXAMPLES = [
    {
        "input": {
            "question": "每个部门有多少员工？",
            "failed_sql": (
                "SELECT d.name, COUNT(u.id) AS user_count "
                "FROM department d JOIN users u ON u.department_id = d.id "
                "GROUP BY d.name"
            ),
            "error_message": 'relation "department" does not exist',
            "schema_context": [
                {"table_name": "departments", "columns": ["id", "name"]},
                {"table_name": "users", "columns": ["id", "department_id"]},
            ],
        },
        "output": {
            "status": "repaired",
            "repaired_sql": (
                "SELECT d.name, COUNT(u.id) AS user_count "
                "FROM departments d "
                "JOIN users u ON u.department_id = d.id "
                "GROUP BY d.id, d.name "
                "ORDER BY user_count DESC"
            ),
            "changes": ["Changed department to departments.", "Grouped by departments.id and departments.name."],
            "tables_used": ["departments", "users"],
            "columns_used": ["departments.id", "departments.name", "users.id", "users.department_id"],
            "explanation": "The table name was corrected to match the provided schema.",
            "safety_checks": {
                "postgresql_dialect": True,
                "read_only": True,
                "uses_only_provided_schema": True,
                "no_invented_tables_or_columns": True,
            },
        },
    }
]


def build_sql_repair_prompt(
    question: str,
    failed_sql: str,
    error_message: str,
    schema_context: list[dict[str, Any]],
    validation_errors: list[str] | None = None,
) -> dict[str, str]:
    payload = {
        "question": question,
        "failed_sql": failed_sql,
        "error_message": error_message,
        "validation_errors": validation_errors or [],
        "schema_context": schema_context,
        "expected_output_schema": EXPECTED_OUTPUT,
        "examples": EXAMPLES,
    }
    return {
        "system": SYSTEM_PROMPT,
        "user": (
            "Repair the SQL if it can be repaired safely. "
            "Return exactly one valid JSON object and no extra text.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        ),
    }
