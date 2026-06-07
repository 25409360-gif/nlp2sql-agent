import json
from typing import Any


SYSTEM_PROMPT = """You are the SQL generation component of an NLP2SQL agent.
Generate safe, read-only PostgreSQL SQL from the provided structured input.
Return exactly one JSON object and no markdown.

Critical safety rules:
1. Use PostgreSQL dialect only.
2. Generate SELECT queries only.
3. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, COPY, CALL, EXECUTE, or transaction-control statements.
4. Use only tables and columns that appear in the provided schema context.
5. Do not invent tables, columns, enum values, relationships, or business definitions.
6. If the schema context is insufficient, return status = "needs_clarification" with sql = null.
7. Prefer explicit JOIN conditions from the schema relationships.
8. Use clear aliases, stable ordering, and LIMIT for ranking or row-list queries unless the user asks otherwise."""


EXPECTED_OUTPUT = {
    "status": "success | needs_clarification | unsupported",
    "sql": "string or null",
    "tables_used": [],
    "columns_used": [],
    "assumptions": [],
    "explanation": "short user-facing explanation",
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
            "question": "谁迟到次数最多？",
            "intent": {
                "intent_type": "ranking_query",
                "entities": {"metrics": ["late count"], "limit": 1},
            },
            "schema_context": [
                {
                    "table_name": "attendance_records",
                    "columns": ["id", "user_id", "status", "work_date"],
                },
                {
                    "table_name": "users",
                    "columns": ["id", "name", "department_id"],
                },
            ],
        },
        "output": {
            "status": "success",
            "sql": (
                "SELECT u.name, COUNT(*) AS late_count "
                "FROM attendance_records ar "
                "JOIN users u ON ar.user_id = u.id "
                "WHERE ar.status = 'late' "
                "GROUP BY u.id, u.name "
                "ORDER BY late_count DESC "
                "LIMIT 1"
            ),
            "tables_used": ["attendance_records", "users"],
            "columns_used": ["attendance_records.user_id", "attendance_records.status", "users.id", "users.name"],
            "assumptions": ["Late attendance is represented by attendance_records.status = 'late'."],
            "explanation": "Counts late attendance records by user and returns the top user.",
            "safety_checks": {
                "postgresql_dialect": True,
                "read_only": True,
                "uses_only_provided_schema": True,
                "no_invented_tables_or_columns": True,
            },
        },
    },
    {
        "input": {
            "question": "删除迟到记录",
            "intent": {"intent_type": "unsupported"},
            "schema_context": [{"table_name": "attendance_records", "columns": ["id", "status"]}],
        },
        "output": {
            "status": "unsupported",
            "sql": None,
            "tables_used": [],
            "columns_used": [],
            "assumptions": [],
            "explanation": "The request is destructive and cannot be answered with a read-only query.",
            "safety_checks": {
                "postgresql_dialect": True,
                "read_only": True,
                "uses_only_provided_schema": True,
                "no_invented_tables_or_columns": True,
            },
        },
    },
    {
        "input": {
            "question": "哪些项目任务还没完成？",
            "intent": {
                "intent_type": "join_query",
                "entities": {
                    "tables": ["tasks", "projects"],
                    "filters": ["task status indicates incomplete"],
                },
            },
            "schema_context": [
                {
                    "table_name": "tasks",
                    "columns": ["id", "project_id", "title", "status"],
                    "content": (
                        "Columns:\n"
                        "- status (VARCHAR(40)): 任务状态，例如 todo、in_progress、review、blocked、done；"
                        "done 表示已完成，其他状态表示未完成"
                    ),
                },
                {
                    "table_name": "projects",
                    "columns": ["id", "name"],
                },
            ],
        },
        "output": {
            "status": "success",
            "sql": (
                "SELECT p.name AS project_name, t.id AS task_id, t.title, t.status "
                "FROM tasks t "
                "JOIN projects p ON t.project_id = p.id "
                "WHERE t.status <> 'done' "
                "ORDER BY p.name, t.id "
                "LIMIT 100"
            ),
            "tables_used": ["tasks", "projects"],
            "columns_used": ["tasks.project_id", "tasks.id", "tasks.title", "tasks.status", "projects.id", "projects.name"],
            "assumptions": ["Task status done means completed; all other statuses are treated as incomplete."],
            "explanation": "Lists tasks whose status is not done and joins each task to its project.",
            "safety_checks": {
                "postgresql_dialect": True,
                "read_only": True,
                "uses_only_provided_schema": True,
                "no_invented_tables_or_columns": True,
            },
        },
    },
]


def build_sql_generation_prompt(
    question: str,
    intent: dict[str, Any],
    schema_context: list[dict[str, Any]],
    conversation_context: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    payload = {
        "question": question,
        "intent": intent,
        "schema_context": schema_context,
        "conversation_context": conversation_context or [],
        "expected_output_schema": EXPECTED_OUTPUT,
        "examples": EXAMPLES,
    }
    return {
        "system": SYSTEM_PROMPT,
        "user": (
            "Generate one safe PostgreSQL SELECT query from this structured input. "
            "Return exactly one valid JSON object and no extra text.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        ),
    }
