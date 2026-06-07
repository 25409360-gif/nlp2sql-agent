import json
from typing import Any


INTENT_TYPES = [
    "simple_lookup",
    "aggregate_query",
    "ranking_query",
    "time_series_query",
    "join_query",
    "follow_up_query",
    "unsupported",
]


SYSTEM_PROMPT = """You are the intent analysis component of an NLP2SQL agent.
Classify the user's database question and return one compact JSON object.
Do not write SQL in this step.
Do not invent tables, columns, metrics, or filters that are not implied by the user input.
If the user request is not a database query, mark it as unsupported."""


EXPECTED_OUTPUT = {
    "intent_type": "simple_lookup | aggregate_query | ranking_query | time_series_query | join_query | follow_up_query | unsupported",
    "confidence": 0.0,
    "is_follow_up": False,
    "requires_clarification": False,
    "clarification_question": None,
    "entities": {
        "tables": [],
        "metrics": [],
        "filters": [],
        "time_range": None,
        "sort": None,
        "limit": None,
    },
    "reason": "short reason without chain-of-thought",
}


EXAMPLES = [
    {
        "input": {
            "question": "谁迟到次数最多？",
            "conversation_context": [],
        },
        "output": {
            "intent_type": "ranking_query",
            "confidence": 0.88,
            "is_follow_up": False,
            "requires_clarification": False,
            "clarification_question": None,
            "entities": {
                "tables": ["attendance_records", "users"],
                "metrics": ["late count"],
                "filters": ["status = late"],
                "time_range": None,
                "sort": "late count desc",
                "limit": 1,
            },
            "reason": "The question asks for the top user ranked by late attendance count.",
        },
    },
    {
        "input": {
            "question": "把系统删掉",
            "conversation_context": [],
        },
        "output": {
            "intent_type": "unsupported",
            "confidence": 0.95,
            "is_follow_up": False,
            "requires_clarification": False,
            "clarification_question": None,
            "entities": {
                "tables": [],
                "metrics": [],
                "filters": [],
                "time_range": None,
                "sort": None,
                "limit": None,
            },
            "reason": "The request is destructive and not a read-only analytics question.",
        },
    },
]


def build_intent_analysis_prompt(
    question: str,
    conversation_context: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    payload = {
        "question": question,
        "conversation_context": conversation_context or [],
        "allowed_intent_types": INTENT_TYPES,
        "expected_output_schema": EXPECTED_OUTPUT,
        "examples": EXAMPLES,
    }
    return {
        "system": SYSTEM_PROMPT,
        "user": (
            "Analyze the database query intent from this structured input. "
            "Return exactly one valid JSON object and no extra text.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        ),
    }
