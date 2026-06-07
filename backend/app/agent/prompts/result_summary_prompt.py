import json
from typing import Any


SYSTEM_PROMPT = """You are the result summarization component of an NLP2SQL agent.
Summarize SQL query results for the user in clear business language.
Return exactly one JSON object and no markdown.

Rules:
1. Use only the provided rows, columns, SQL, and question.
2. Do not invent numbers, entities, dates, rankings, or explanations.
3. If there are no rows, clearly say no matching data was found.
4. Keep the answer concise.
5. Preserve important units and column meanings when they are provided."""


EXPECTED_OUTPUT = {
    "answer": "short natural-language answer",
    "key_points": [],
    "row_count": 0,
    "limitations": [],
    "follow_up_suggestions": [],
}


EXAMPLES = [
    {
        "input": {
            "question": "谁迟到次数最多？",
            "sql": "SELECT u.name, COUNT(*) AS late_count FROM ... LIMIT 1",
            "columns": ["name", "late_count"],
            "rows": [{"name": "张三", "late_count": 8}],
            "row_count": 1,
        },
        "output": {
            "answer": "张三迟到次数最多，共 8 次。",
            "key_points": ["张三: 8 次"],
            "row_count": 1,
            "limitations": [],
            "follow_up_suggestions": ["可以继续查看张三迟到的具体日期。"],
        },
    },
    {
        "input": {
            "question": "上个月有哪些缺勤记录？",
            "sql": "SELECT ...",
            "columns": ["name", "work_date", "status"],
            "rows": [],
            "row_count": 0,
        },
        "output": {
            "answer": "没有找到符合条件的缺勤记录。",
            "key_points": [],
            "row_count": 0,
            "limitations": ["结果为空只能说明当前数据库中没有匹配记录。"],
            "follow_up_suggestions": ["可以放宽时间范围后再查询。"],
        },
    },
]


def build_result_summary_prompt(
    question: str,
    sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    row_count: int,
    execution_time_ms: float | None = None,
) -> dict[str, str]:
    payload = {
        "question": question,
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "execution_time_ms": execution_time_ms,
        "expected_output_schema": EXPECTED_OUTPUT,
        "examples": EXAMPLES,
    }
    return {
        "system": SYSTEM_PROMPT,
        "user": (
            "Summarize this SQL query result. "
            "Return exactly one valid JSON object and no extra text.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        ),
    }
