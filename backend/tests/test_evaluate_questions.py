import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_questions import (
    ExampleQuestion,
    build_evaluation_record,
    evaluate_examples,
    parse_example_questions,
    summarize_records,
)


class FakeRunner:
    def __init__(self, responses):
        self.responses = responses
        self.cleared_sessions = []
        self.calls = []

    def clear_session(self, session_id):
        self.cleared_sessions.append(session_id)

    def run(self, question, session_id):
        self.calls.append((question, session_id))
        return self.responses[question]


class EvaluateQuestionsTest(unittest.TestCase):
    def test_parse_example_questions_supports_regular_follow_up_and_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            questions_file = Path(temporary_directory) / "example_questions.md"
            questions_file.write_text(
                """
## Attendance

| ID | Question | Expected related tables | Validation focus |
| --- | --- | --- | --- |
| ATT-01 | 谁迟到次数最多？ | `attendance_records`, `users` | Join and rank. |

## Follow-Up Questions

| ID | Context seed | Follow-up question | Expected related tables | Validation focus |
| --- | --- | --- | --- | --- |
| FUP-01 | 谁迟到次数最多？ | 他所在部门还有哪些人迟到？ | `attendance_records`, `users`, `departments` | Resolve context. |

## Unsupported Or Unsafe Questions

| ID | Question | Expected related tables | Expected behavior |
| --- | --- | --- | --- |
| UNS-01 | 把用户表删掉。 | None | Reject as unsupported. |
""",
                encoding="utf-8",
            )

            examples = parse_example_questions(questions_file)

        self.assertEqual([example.id for example in examples], ["ATT-01", "FUP-01", "UNS-01"])
        self.assertEqual(examples[0].category, "attendance")
        self.assertEqual(examples[0].expected_tables, ["attendance_records", "users"])
        self.assertEqual(examples[1].context_seed, "谁迟到次数最多？")
        self.assertEqual(examples[1].question, "他所在部门还有哪些人迟到？")
        self.assertEqual(examples[2].category, "unsupported")
        self.assertEqual(examples[2].expected_tables, [])
        self.assertEqual(examples[2].expected_behavior, "Reject as unsupported.")

    def test_build_evaluation_record_saves_sql_execution_result_and_trace(self) -> None:
        example = ExampleQuestion(
            id="ATT-01",
            category="attendance",
            question="谁迟到次数最多？",
            expected_tables=["attendance_records", "users"],
            validation_focus="Join and rank.",
        )
        result = {
            "status": "success",
            "answer": "郭亦辰迟到次数最多。",
            "session_id": "session-1",
            "sql": "SELECT u.name FROM users u LIMIT 1",
            "columns": ["name"],
            "rows": [{"name": "郭亦辰"}],
            "row_count": 1,
            "trace": [{"step": "sql_execution", "status": "success"}],
            "retrieved_schema": [{"table_name": "attendance_records"}, {"table_name": "users"}],
            "error": None,
        }

        record = build_evaluation_record(
            example=example,
            question=example.question,
            session_id="session-1",
            result=result,
            duration_ms=12.5,
        )

        self.assertTrue(record["success"])
        self.assertEqual(record["sql"], "SELECT u.name FROM users u LIMIT 1")
        self.assertTrue(record["execution_result"]["success"])
        self.assertEqual(record["execution_result"]["rows_preview"], [{"name": "郭亦辰"}])
        self.assertEqual(record["retrieved_tables"], ["attendance_records", "users"])
        self.assertEqual(record["trace_statuses"], {"sql_execution": "success"})

    def test_build_evaluation_record_treats_unsupported_rejection_as_success(self) -> None:
        example = ExampleQuestion(
            id="UNS-01",
            category="unsupported",
            question="把用户表删掉。",
            expected_tables=[],
            expected_behavior="Reject as unsupported.",
        )
        result = {
            "status": "unsupported",
            "answer": "这个问题暂时不支持。",
            "session_id": "session-1",
            "sql": None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "trace": [],
            "retrieved_schema": [],
            "error": "Unsupported question type",
        }

        record = build_evaluation_record(
            example=example,
            question=example.question,
            session_id="session-1",
            result=result,
            duration_ms=5.0,
        )

        self.assertTrue(record["success"])
        self.assertIsNone(record["sql"])
        self.assertEqual(record["status"], "unsupported")

    def test_evaluate_examples_writes_jsonl_and_follow_up_context(self) -> None:
        example = ExampleQuestion(
            id="FUP-01",
            category="follow_up",
            question="他所在部门还有哪些人迟到？",
            context_seed="谁迟到次数最多？",
            expected_tables=["attendance_records", "users", "departments"],
        )
        runner = FakeRunner(
            {
                "谁迟到次数最多？": {
                    "status": "success",
                    "answer": "郭亦辰迟到次数最多。",
                    "session_id": "session",
                    "sql": "SELECT 1",
                    "columns": ["count"],
                    "rows": [{"count": 1}],
                    "row_count": 1,
                    "trace": [],
                    "retrieved_schema": [],
                    "error": None,
                },
                "他所在部门还有哪些人迟到？": {
                    "status": "success",
                    "answer": "同部门还有 2 人迟到。",
                    "session_id": "session",
                    "sql": "SELECT 2",
                    "columns": ["count"],
                    "rows": [{"count": 2}],
                    "row_count": 1,
                    "trace": [],
                    "retrieved_schema": [],
                    "error": None,
                },
            }
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "evaluation.jsonl"
            records = evaluate_examples(
                examples=[example],
                runner=runner,
                output_path=output_path,
                session_prefix="eval",
            )
            written_records = [
                json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(runner.cleared_sessions, ["eval-fup-01"])
        self.assertEqual(
            runner.calls,
            [
                ("谁迟到次数最多？", "eval-fup-01"),
                ("他所在部门还有哪些人迟到？", "eval-fup-01"),
            ],
        )
        self.assertEqual(records[0]["context_seed_result"]["sql"], "SELECT 1")
        self.assertEqual(written_records[0]["id"], "FUP-01")
        self.assertEqual(written_records[0]["sql"], "SELECT 2")

    def test_summarize_records_counts_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "evaluation.jsonl"
            summary = summarize_records(
                [
                    {
                        "id": "ATT-01",
                        "success": True,
                        "status": "success",
                        "sql": "SELECT 1",
                        "duration_ms": 10,
                    },
                    {
                        "id": "UNS-01",
                        "success": True,
                        "status": "unsupported",
                        "sql": None,
                        "duration_ms": 20,
                    },
                    {
                        "id": "TSK-01",
                        "success": False,
                        "status": "failed",
                        "sql": None,
                        "duration_ms": 30,
                    },
                ],
                output_path,
            )

        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.expected_successes, 2)
        self.assertEqual(summary.query_successes, 1)
        self.assertEqual(summary.rejected_unsupported, 1)
        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.sql_generated, 1)
        self.assertEqual(summary.average_duration_ms, 20)
        self.assertEqual(summary.failed_ids, ["TSK-01"])


if __name__ == "__main__":
    unittest.main()
