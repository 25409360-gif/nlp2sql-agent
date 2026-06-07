import unittest

from app.agent.text2sql_agent import Text2SQLAgent


SCHEMA_MATCHES = [
    {
        "table_name": "users",
        "columns": ["id", "name"],
        "score": 0.9,
        "distance": 0.1,
        "source": "keyword",
        "content": "users table",
    }
]


class FakeMemory:
    def __init__(self) -> None:
        self.loaded_session_id = None
        self.saved = []

    def load(self, session_id):
        self.loaded_session_id = session_id
        return [{"question": "之前的问题", "answer": "之前的答案"}]

    def save(self, session_id, record):
        self.saved.append({"session_id": session_id, "record": record})


class FakeIntentAnalyzer:
    def __init__(self, intent_type="simple_lookup", requires_clarification=False, tables=None) -> None:
        self.intent_type = intent_type
        self.requires_clarification = requires_clarification
        self.tables = tables or ["users"]
        self.last_conversation_context = None

    def analyze(self, question, conversation_context=None):
        self.last_conversation_context = conversation_context or []
        return {
            "intent_type": self.intent_type,
            "confidence": 0.9,
            "is_follow_up": bool(conversation_context),
            "requires_clarification": self.requires_clarification,
            "clarification_question": "你想查哪个时间范围？" if self.requires_clarification else None,
            "entities": {"tables": self.tables, "filters": []},
            "reason": "fake intent",
            "source": "fake",
        }


class FakeSchemaRetriever:
    def __init__(self) -> None:
        self.calls = []

    def retrieve(
        self,
        question,
        top_k=5,
        refresh_index=False,
        use_keyword_fallback=True,
        preferred_table_names=None,
        restrict_to_preferred=False,
    ):
        self.calls.append(
            {
                "question": question,
                "preferred_table_names": preferred_table_names or [],
                "restrict_to_preferred": restrict_to_preferred,
            }
        )
        return {"question": question, "matches": SCHEMA_MATCHES}


class VerboseFakeMemory(FakeMemory):
    def load(self, session_id):
        self.loaded_session_id = session_id
        return [
            {
                "question": "上一问",
                "answer": "上一答",
                "sql": "SELECT id, name FROM users",
                "status": "success",
                "columns": ["id", "name"],
                "rows": [{"id": 1, "name": "王子轩"}],
                "row_count": 1,
            }
        ]


class AttendanceOnlySchemaRetriever:
    def retrieve(
        self,
        question,
        top_k=5,
        refresh_index=False,
        use_keyword_fallback=True,
        preferred_table_names=None,
        restrict_to_preferred=False,
    ):
        return {
            "question": question,
            "matches": [
                {
                    "table_name": "attendance_records",
                    "columns": ["id", "user_id", "status"],
                    "score": 0.9,
                    "distance": 0.1,
                    "source": "keyword",
                    "content": "attendance table",
                }
            ],
        }


class FakeSchemaService:
    def list_tables(self):
        return [{"name": "users"}, {"name": "attendance_records"}]

    def get_table_schema(self, table_name):
        schemas = {
            "users": {
                "name": "users",
                "description": "users table",
                "columns": [{"name": "id", "type": "INTEGER"}, {"name": "name", "type": "VARCHAR(120)"}],
                "foreign_keys": [],
            },
            "attendance_records": {
                "name": "attendance_records",
                "description": "attendance table",
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "user_id", "type": "INTEGER"},
                    {"name": "status", "type": "VARCHAR(40)"},
                ],
                "foreign_keys": [{"referred_table": "users"}],
            },
        }
        return schemas.get(table_name)


class FakeSQLGenerator:
    def __init__(self, sql="SELECT u.id, u.name FROM users u LIMIT 5") -> None:
        self.sql = sql
        self.calls = 0

    def generate(self, question, intent_result, schema_context, conversation_context=None):
        self.calls += 1
        return {
            "status": "success",
            "sql": self.sql,
            "tables_used": ["users"],
            "columns_used": ["users.id", "users.name"],
            "assumptions": [],
            "explanation": "fake sql",
            "safety_checks": {
                "postgresql_dialect": True,
                "read_only": True,
                "uses_only_provided_schema": True,
                "no_invented_tables_or_columns": True,
            },
            "source": "fake",
        }


class FakeSQLValidator:
    def validate(self, sql, schema_context=None):
        return {
            "valid": True,
            "safe_sql": sql,
            "original_sql": sql,
            "referenced_tables": ["users"],
            "referenced_columns": ["users.id", "users.name"],
            "error": None,
            "limit_applied": 5,
        }


class FakeSQLExecutor:
    def __init__(self, success=True) -> None:
        self.success = success
        self.calls = 0

    def execute(self, validation_result):
        self.calls += 1
        if not self.success:
            return {
                "success": False,
                "sql": validation_result["safe_sql"],
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 1.1,
                "truncated": False,
                "error": "column users.full_name does not exist",
            }
        return {
            "success": True,
            "sql": validation_result["safe_sql"],
            "columns": ["id", "name"],
            "rows": [{"id": 1, "name": "王子轩"}],
            "row_count": 1,
            "execution_time_ms": 1.1,
            "truncated": False,
            "error": None,
        }


class FakeSQLRepairer:
    def __init__(self) -> None:
        self.calls = 0

    def repair(self, question, failed_sql, error_message, schema_context, validation_errors=None):
        self.calls += 1
        repaired_sql = "SELECT u.id, u.name FROM users u LIMIT 5"
        return {
            "status": "repaired",
            "repaired_sql": repaired_sql,
            "failure_reason": None,
            "changes": ["Changed u.full_name to u.name."],
            "tables_used": ["users"],
            "columns_used": ["users.id", "users.name"],
            "explanation": "fake repair",
            "validation_result": {
                "valid": True,
                "safe_sql": repaired_sql,
                "original_sql": repaired_sql,
                "referenced_tables": ["users"],
                "referenced_columns": ["users.id", "users.name"],
                "error": None,
                "limit_applied": 5,
            },
            "execution_result": {
                "success": True,
                "sql": repaired_sql,
                "columns": ["id", "name"],
                "rows": [{"id": 1, "name": "王子轩"}],
                "row_count": 1,
                "execution_time_ms": 1.3,
                "truncated": False,
                "error": None,
            },
            "attempts": [{"attempt": 1, "status": "repaired"}],
            "source": "fake",
        }


class FakeResultSummarizer:
    def summarize(self, question, sql, execution_result):
        return {
            "answer": "查到 1 个用户：王子轩。",
            "key_points": ["王子轩"],
            "row_count": execution_result["row_count"],
            "limitations": [],
            "follow_up_suggestions": [],
            "source": "fake",
        }


class FakeTextMatchSQLBuilder:
    def __init__(self, result=None) -> None:
        self.result = result
        self.calls = 0

    def build(self, question, intent_result, schema_context):
        self.calls += 1
        return self.result


class Text2SQLAgentTest(unittest.TestCase):
    def make_agent(
        self,
        executor=None,
        repairer=None,
        intent_analyzer=None,
        sql_generator=None,
        text_match_sql_builder=None,
        schema_retriever=None,
    ):
        return Text2SQLAgent(
            intent_analyzer=intent_analyzer or FakeIntentAnalyzer(),
            schema_retriever=schema_retriever or FakeSchemaRetriever(),
            sql_generator=sql_generator or FakeSQLGenerator(),
            sql_validator=FakeSQLValidator(),
            sql_executor=executor or FakeSQLExecutor(),
            sql_repairer=repairer or FakeSQLRepairer(),
            result_summarizer=FakeResultSummarizer(),
            memory_manager=FakeMemory(),
            schema_service=FakeSchemaService(),
            text_match_sql_builder=text_match_sql_builder,
        )

    def test_complete_happy_path(self) -> None:
        executor = FakeSQLExecutor(success=True)
        repairer = FakeSQLRepairer()
        agent = self.make_agent(executor=executor, repairer=repairer)

        result = agent.run("列出用户", "session-1")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["answer"], "查到 1 个用户：王子轩。")
        self.assertEqual(result["sql"], "SELECT u.id, u.name FROM users u LIMIT 5")
        self.assertEqual(result["columns"], ["id", "name"])
        self.assertEqual(result["rows"], [{"id": 1, "name": "王子轩"}])
        self.assertEqual(result["retrieved_schema"][0]["table_name"], "users")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(repairer.calls, 0)
        saved_record = agent.memory_manager.saved[-1]["record"]
        self.assertEqual(saved_record["columns"], ["id", "name"])
        self.assertEqual(saved_record["rows"], [{"id": 1, "name": "王子轩"}])
        self.assertIn("result_summary", self._trace_steps(result))
        self.assertIn({"step": "sql_repair", "status": "skipped"}, self._trace_step_status_pairs(result))

    def test_execution_failure_then_repair_path(self) -> None:
        repairer = FakeSQLRepairer()
        agent = self.make_agent(executor=FakeSQLExecutor(success=False), repairer=repairer)

        result = agent.run("列出用户", "session-2")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sql"], "SELECT u.id, u.name FROM users u LIMIT 5")
        self.assertEqual(result["repair_result"]["status"], "repaired")
        self.assertEqual(repairer.calls, 1)
        self.assertIn({"step": "sql_execution", "status": "failed"}, self._trace_step_status_pairs(result))
        self.assertIn({"step": "sql_repair", "status": "success"}, self._trace_step_status_pairs(result))

    def test_schema_context_enrichment_adds_related_tables(self) -> None:
        agent = Text2SQLAgent(
            intent_analyzer=FakeIntentAnalyzer(tables=["attendance_records"]),
            schema_retriever=AttendanceOnlySchemaRetriever(),
            sql_generator=FakeSQLGenerator(),
            sql_validator=FakeSQLValidator(),
            sql_executor=FakeSQLExecutor(),
            sql_repairer=FakeSQLRepairer(),
            result_summarizer=FakeResultSummarizer(),
            memory_manager=FakeMemory(),
            schema_service=FakeSchemaService(),
            text_match_sql_builder=FakeTextMatchSQLBuilder(),
        )

        result = agent.run("谁迟到最多？", "session-relationship")

        tables = [item["table_name"] for item in result["retrieved_schema"]]
        self.assertIn("attendance_records", tables)
        self.assertIn("users", tables)
        self.assertIn(
            {"step": "schema_context_enrichment", "status": "success"},
            self._trace_step_status_pairs(result),
        )

    def test_text_match_sql_is_used_before_llm_generation(self) -> None:
        sql_generator = FakeSQLGenerator()
        text_match_sql = "SELECT u.id, u.name FROM users u WHERE u.name ILIKE '%王子轩%' LIMIT 20"
        text_match_builder = FakeTextMatchSQLBuilder(
            {
                "sql": text_match_sql,
                "table_name": "users",
                "terms": ["王子轩"],
                "text_columns": ["name"],
                "selected_columns": ["id", "name"],
                "threshold": 1,
                "reason": "fake text match",
                "source": "text_match",
            }
        )
        agent = self.make_agent(
            sql_generator=sql_generator,
            text_match_sql_builder=text_match_builder,
        )

        result = agent.run("王子轩是谁？", "session-text-match")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sql"], text_match_sql)
        self.assertEqual(result["sql_generation"]["source"], "text_match")
        self.assertEqual(text_match_builder.calls, 1)
        self.assertEqual(sql_generator.calls, 0)

    def test_default_text_match_builder_reads_schema_through_agent(self) -> None:
        sql_generator = FakeSQLGenerator()
        agent = self.make_agent(sql_generator=sql_generator)

        result = agent.run("王子轩是谁？", "session-default-text-match")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sql_generation"]["source"], "text_match")
        self.assertIn("ILIKE '%王子%'", result["sql"])
        self.assertEqual(sql_generator.calls, 0)

    def test_selected_table_is_passed_as_restricted_schema_scope(self) -> None:
        schema_retriever = FakeSchemaRetriever()
        agent = self.make_agent(
            schema_retriever=schema_retriever,
            text_match_sql_builder=FakeTextMatchSQLBuilder(),
        )

        result = agent.run("列出用户", "session-scoped", selected_table_name="users")

        self.assertEqual(result["status"], "success")
        self.assertEqual(schema_retriever.calls[0]["preferred_table_names"], ["users"])
        self.assertTrue(schema_retriever.calls[0]["restrict_to_preferred"])

    def test_loaded_memory_excludes_saved_result_rows_from_agent_context(self) -> None:
        intent_analyzer = FakeIntentAnalyzer()
        agent = Text2SQLAgent(
            intent_analyzer=intent_analyzer,
            schema_retriever=FakeSchemaRetriever(),
            sql_generator=FakeSQLGenerator(),
            sql_validator=FakeSQLValidator(),
            sql_executor=FakeSQLExecutor(),
            sql_repairer=FakeSQLRepairer(),
            result_summarizer=FakeResultSummarizer(),
            memory_manager=VerboseFakeMemory(),
            schema_service=FakeSchemaService(),
            text_match_sql_builder=FakeTextMatchSQLBuilder(),
        )

        agent.run("列出用户", "session-context")

        self.assertEqual(len(intent_analyzer.last_conversation_context), 1)
        self.assertNotIn("rows", intent_analyzer.last_conversation_context[0])
        self.assertNotIn("columns", intent_analyzer.last_conversation_context[0])

    def test_unsupported_question_skips_sql_steps(self) -> None:
        agent = self.make_agent(intent_analyzer=FakeIntentAnalyzer(intent_type="unsupported"))

        result = agent.run("把用户删掉", "session-3")

        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["sql"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["error_code"], "unsupported_request")
        self.assertIn("暂时不支持", result["error"])
        self.assertIn({"step": "sql_generation", "status": "skipped"}, self._trace_step_status_pairs(result))
        self.assertIn({"step": "result_summary", "status": "skipped"}, self._trace_step_status_pairs(result))

    def _trace_steps(self, result):
        return [event["step"] for event in result["trace"]]

    def _trace_step_status_pairs(self, result):
        return [{"step": event["step"], "status": event["status"]} for event in result["trace"]]


if __name__ == "__main__":
    unittest.main()
