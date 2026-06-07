#!/usr/bin/env python3
"""Run the example question set through the NLP2SQL flow and save results."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_OUTPUT_NAME = "manual_evaluation_results.jsonl"
ROWS_PREVIEW_LIMIT = 5


@dataclass(frozen=True)
class ExampleQuestion:
    id: str
    category: str
    question: str
    expected_tables: list[str]
    validation_focus: str = ""
    expected_behavior: str = ""
    context_seed: str = ""


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    expected_successes: int
    query_successes: int
    rejected_unsupported: int
    failures: int
    sql_generated: int
    average_duration_ms: float
    output_path: str
    failed_ids: list[str]


CATEGORY_BY_HEADING = {
    "Attendance": "attendance",
    "Device Usage": "device_usage",
    "Projects": "projects",
    "Tasks": "tasks",
    "Meetings": "meetings",
    "Multi-Table Analysis": "multi_table",
    "Follow-Up Questions": "follow_up",
    "Unsupported Or Unsafe Questions": "unsupported",
}

CATEGORY_BY_ID_PREFIX = {
    "ATT": "attendance",
    "DEV": "device_usage",
    "PRJ": "projects",
    "TSK": "tasks",
    "MTG": "meetings",
    "MUL": "multi_table",
    "FUP": "follow_up",
    "UNS": "unsupported",
}


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        if (
            (candidate / "README.md").exists()
            and (candidate / "docker-compose.yml").exists()
            and (candidate / "docs" / "example_questions.md").exists()
        ):
            return candidate

    return Path.cwd().resolve()


def default_questions_file() -> Path:
    return find_repo_root() / "docs" / "example_questions.md"


def default_output_file() -> Path:
    return find_repo_root() / "data" / DEFAULT_OUTPUT_NAME


def parse_example_questions(path: Path) -> list[ExampleQuestion]:
    current_heading = ""
    examples: list[ExampleQuestion] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if line.startswith("## "):
            heading = line.removeprefix("## ").strip()
            current_heading = CATEGORY_BY_HEADING.get(heading, "")
            continue

        cells = split_markdown_row(line)
        if not cells or is_markdown_table_header(cells):
            continue

        question_id = cells[0].strip()
        category = current_heading or category_from_id(question_id)
        if not category:
            continue

        if category == "follow_up":
            if len(cells) < 5:
                continue
            examples.append(
                ExampleQuestion(
                    id=question_id,
                    category=category,
                    question=clean_cell(cells[2]),
                    context_seed=clean_cell(cells[1]),
                    expected_tables=parse_expected_tables(cells[3]),
                    validation_focus=clean_cell(cells[4]),
                )
            )
            continue

        if category == "unsupported":
            if len(cells) < 4:
                continue
            examples.append(
                ExampleQuestion(
                    id=question_id,
                    category=category,
                    question=clean_cell(cells[1]),
                    expected_tables=parse_expected_tables(cells[2]),
                    expected_behavior=clean_cell(cells[3]),
                )
            )
            continue

        if len(cells) < 4:
            continue
        examples.append(
            ExampleQuestion(
                id=question_id,
                category=category,
                question=clean_cell(cells[1]),
                expected_tables=parse_expected_tables(cells[2]),
                validation_focus=clean_cell(cells[3]),
            )
        )

    return examples


def split_markdown_row(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        return []
    return [cell.strip() for cell in line.strip("|").split("|")]


def is_markdown_table_header(cells: list[str]) -> bool:
    if not cells:
        return True
    if cells[0].lower() == "id":
        return True
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def category_from_id(question_id: str) -> str:
    prefix = question_id.split("-", maxsplit=1)[0].upper()
    return CATEGORY_BY_ID_PREFIX.get(prefix, "")


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ")).strip()


def parse_expected_tables(value: str) -> list[str]:
    cleaned = clean_cell(value)
    if not cleaned or cleaned.lower() == "none":
        return []

    tables = re.findall(r"`([^`]+)`", cleaned)
    if not tables:
        tables = [part.strip() for part in cleaned.split(",")]

    return [table.strip().strip("`") for table in tables if table.strip()]


def filter_examples(
    examples: list[ExampleQuestion],
    include_follow_ups: bool,
    include_unsupported: bool,
    limit: int | None,
) -> list[ExampleQuestion]:
    filtered = [
        example
        for example in examples
        if (include_follow_ups or example.category != "follow_up")
        and (include_unsupported or example.category != "unsupported")
    ]
    if limit is not None:
        return filtered[:limit]
    return filtered


class ChatAPIRunner:
    def __init__(self, api_base_url: str, timeout: float) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout

    def run(self, question: str, session_id: str) -> dict[str, Any]:
        payload = json.dumps({"question": question, "session_id": session_id}).encode("utf-8")
        request = urllib.request.Request(
            self.chat_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def clear_session(self, session_id: str) -> None:
        encoded_session_id = urllib.parse.quote(session_id, safe="")
        request = urllib.request.Request(
            f"{self.sessions_url}/{encoded_session_id}",
            method="DELETE",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                return
        except (urllib.error.URLError, TimeoutError):
            return

    @property
    def chat_url(self) -> str:
        if self.api_base_url.endswith("/api"):
            return f"{self.api_base_url}/chat"
        return f"{self.api_base_url}/api/chat"

    @property
    def sessions_url(self) -> str:
        if self.api_base_url.endswith("/api"):
            return f"{self.api_base_url}/sessions"
        return f"{self.api_base_url}/api/sessions"


class AgentRunner:
    def __init__(self) -> None:
        backend_root = Path(__file__).resolve().parents[1]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))

        from app.agent.memory_manager import ConversationMemoryManager
        from app.agent.text2sql_agent import Text2SQLAgent

        self.memory_manager = ConversationMemoryManager()
        self.agent = Text2SQLAgent(memory_manager=self.memory_manager)

    def run(self, question: str, session_id: str) -> dict[str, Any]:
        return self.agent.run(question=question, session_id=session_id)

    def clear_session(self, session_id: str) -> None:
        self.memory_manager.clear(session_id)


def create_runner(mode: str, api_base_url: str, timeout: float) -> ChatAPIRunner | AgentRunner:
    if mode == "api":
        return ChatAPIRunner(api_base_url=api_base_url, timeout=timeout)
    if mode == "agent":
        return AgentRunner()
    raise ValueError(f"Unsupported mode: {mode}")


def evaluate_examples(
    examples: list[ExampleQuestion],
    runner: ChatAPIRunner | AgentRunner,
    output_path: Path,
    session_prefix: str,
    clear_sessions: bool = True,
) -> list[dict[str, Any]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    with output_path.open("w", encoding="utf-8") as output_file:
        for example in examples:
            session_id = f"{session_prefix}-{example.id.lower()}"
            if clear_sessions:
                runner.clear_session(session_id)

            context_record: dict[str, Any] | None = None
            if example.context_seed:
                context_record = run_question(
                    runner=runner,
                    question=example.context_seed,
                    session_id=session_id,
                    example=example,
                    is_context_seed=True,
                )

            record = run_question(
                runner=runner,
                question=example.question,
                session_id=session_id,
                example=example,
                is_context_seed=False,
                context_record=context_record,
            )
            records.append(record)
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            output_file.flush()

    return records


def run_question(
    runner: ChatAPIRunner | AgentRunner,
    question: str,
    session_id: str,
    example: ExampleQuestion,
    is_context_seed: bool,
    context_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()

    try:
        result = runner.run(question=question, session_id=session_id)
    except Exception as exc:
        result = {
            "status": "error",
            "answer": "",
            "session_id": session_id,
            "sql": None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "trace": [],
            "retrieved_schema": [],
            "error": str(exc),
        }

    duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
    record = build_evaluation_record(
        example=example,
        question=question,
        session_id=session_id,
        result=result,
        duration_ms=duration_ms,
        is_context_seed=is_context_seed,
    )

    if context_record:
        record["context_seed_result"] = {
            "status": context_record["status"],
            "success": context_record["success"],
            "answer": context_record["answer"],
            "sql": context_record["sql"],
            "row_count": context_record["row_count"],
            "error": context_record["error"],
            "duration_ms": context_record["duration_ms"],
        }

    return record


def build_evaluation_record(
    example: ExampleQuestion,
    question: str,
    session_id: str,
    result: dict[str, Any],
    duration_ms: float,
    is_context_seed: bool = False,
) -> dict[str, Any]:
    rows = result.get("rows") or []
    trace = result.get("trace") or []
    retrieved_schema = result.get("retrieved_schema") or []
    execution_result = result.get("execution_result") or {}

    record = {
        "id": example.id,
        "category": example.category,
        "question": question,
        "context_seed": example.context_seed,
        "is_context_seed": is_context_seed,
        "session_id": session_id,
        "expected_tables": example.expected_tables,
        "validation_focus": example.validation_focus,
        "expected_behavior": example.expected_behavior,
        "status": result.get("status") or "unknown",
        "success": is_expected_success(example, result),
        "answer": result.get("answer") or "",
        "sql": result.get("sql"),
        "columns": result.get("columns") or execution_result.get("columns") or [],
        "row_count": int(result.get("row_count") or execution_result.get("row_count") or 0),
        "rows_preview": rows[:ROWS_PREVIEW_LIMIT],
        "truncated": bool(execution_result.get("truncated", False)),
        "error": result.get("error") or execution_result.get("error"),
        "execution_result": normalize_execution_result(result),
        "retrieved_tables": [
            item.get("table_name")
            for item in retrieved_schema
            if isinstance(item, dict) and item.get("table_name")
        ],
        "trace_statuses": trace_statuses(trace),
        "duration_ms": duration_ms,
    }
    return record


def normalize_execution_result(result: dict[str, Any]) -> dict[str, Any]:
    execution_result = result.get("execution_result")
    if isinstance(execution_result, dict):
        rows = execution_result.get("rows") or []
        return {
            "success": bool(execution_result.get("success")),
            "columns": execution_result.get("columns") or [],
            "row_count": int(execution_result.get("row_count") or 0),
            "rows_preview": rows[:ROWS_PREVIEW_LIMIT],
            "truncated": bool(execution_result.get("truncated", False)),
            "error": execution_result.get("error"),
        }

    return {
        "success": result.get("status") == "success",
        "columns": result.get("columns") or [],
        "row_count": int(result.get("row_count") or 0),
        "rows_preview": (result.get("rows") or [])[:ROWS_PREVIEW_LIMIT],
        "truncated": False,
        "error": result.get("error"),
    }


def trace_statuses(trace: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(event.get("step")): str(event.get("status"))
        for event in trace
        if isinstance(event, dict) and event.get("step")
    }


def is_expected_success(example: ExampleQuestion, result: dict[str, Any]) -> bool:
    status = result.get("status")
    sql = result.get("sql")
    error = result.get("error")

    if example.category == "unsupported":
        return status == "unsupported" and not sql

    return status == "success" and bool(sql) and not error


def summarize_records(records: list[dict[str, Any]], output_path: Path) -> EvaluationSummary:
    if records:
        average_duration_ms = round(
            sum(float(record.get("duration_ms") or 0) for record in records) / len(records),
            3,
        )
    else:
        average_duration_ms = 0.0

    return EvaluationSummary(
        total=len(records),
        expected_successes=sum(1 for record in records if record.get("success")),
        query_successes=sum(1 for record in records if record.get("status") == "success"),
        rejected_unsupported=sum(1 for record in records if record.get("status") == "unsupported"),
        failures=sum(1 for record in records if not record.get("success")),
        sql_generated=sum(1 for record in records if record.get("sql")),
        average_duration_ms=average_duration_ms,
        output_path=str(output_path),
        failed_ids=[str(record.get("id")) for record in records if not record.get("success")],
    )


def print_summary(summary: EvaluationSummary) -> None:
    print("Manual evaluation summary")
    print(f"- total: {summary.total}")
    print(f"- expected_successes: {summary.expected_successes}")
    print(f"- query_successes: {summary.query_successes}")
    print(f"- rejected_unsupported: {summary.rejected_unsupported}")
    print(f"- failures: {summary.failures}")
    print(f"- sql_generated: {summary.sql_generated}")
    print(f"- average_duration_ms: {summary.average_duration_ms}")
    print(f"- output_path: {summary.output_path}")
    if summary.failed_ids:
        print(f"- failed_ids: {', '.join(summary.failed_ids)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate docs/example_questions.md through the NLP2SQL chat API or Agent.",
    )
    parser.add_argument(
        "--questions-file",
        type=Path,
        default=default_questions_file(),
        help="Path to docs/example_questions.md.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_file(),
        help="JSONL file to write evaluation records.",
    )
    parser.add_argument(
        "--mode",
        choices=["api", "agent"],
        default="api",
        help="Use the running chat API or instantiate Text2SQLAgent directly.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help="Backend base URL for --mode api.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=90.0,
        help="HTTP timeout in seconds for --mode api.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of examples to evaluate after filters.",
    )
    parser.add_argument(
        "--session-prefix",
        default=f"manual-eval-{int(time.time())}",
        help="Prefix used to create isolated session IDs.",
    )
    parser.add_argument(
        "--skip-follow-ups",
        action="store_true",
        help="Skip follow-up examples.",
    )
    parser.add_argument(
        "--skip-unsupported",
        action="store_true",
        help="Skip unsupported or unsafe examples.",
    )
    parser.add_argument(
        "--no-clear-session",
        action="store_true",
        help="Do not clear each generated session before running an example.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with status 1 when any example does not meet the expected outcome.",
    )
    return parser


def main(argv: list[str] | None = None, runner_factory: Callable[..., Any] = create_runner) -> int:
    args = build_parser().parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        print("--limit must be greater than 0", file=sys.stderr)
        return 2

    questions_file = args.questions_file.resolve()
    output_path = args.output.resolve()

    if not questions_file.exists():
        print(f"Questions file not found: {questions_file}", file=sys.stderr)
        return 2

    examples = parse_example_questions(questions_file)
    selected_examples = filter_examples(
        examples,
        include_follow_ups=not args.skip_follow_ups,
        include_unsupported=not args.skip_unsupported,
        limit=args.limit,
    )

    runner = runner_factory(args.mode, args.api_base_url, args.timeout)
    records = evaluate_examples(
        examples=selected_examples,
        runner=runner,
        output_path=output_path,
        session_prefix=args.session_prefix,
        clear_sessions=not args.no_clear_session,
    )
    summary = summarize_records(records, output_path)
    print_summary(summary)

    if args.fail_on_error and summary.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
