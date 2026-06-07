import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.intent_analyzer import IntentAnalyzer
from app.agent.result_summarizer import ResultSummarizer
from app.agent.sql_executor import SQLExecutor
from app.agent.sql_generator import SQLGenerator
from app.agent.sql_repairer import SQLRepairer
from app.agent.sql_validator import SQLValidator
from app.agent.text_match_sql import TextMatchSQLBuilder
from app.core.logging import get_logger, sanitize_for_log
from app.schemas.trace import TraceEvent, append_trace_event, trace_events_to_dicts
from app.services.schema_retriever import SchemaRetriever
from app.utils.error_handling import classify_error, failed_step_from_trace

logger = get_logger(__name__)


@dataclass
class Text2SQLAgentResult:
    status: str
    answer: str
    session_id: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    retrieved_schema: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    intent: dict[str, Any] | None = None
    sql_generation: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    repair_result: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Text2SQLAgent:
    def __init__(
        self,
        intent_analyzer: IntentAnalyzer | None = None,
        schema_retriever: SchemaRetriever | None = None,
        sql_generator: SQLGenerator | None = None,
        sql_validator: SQLValidator | None = None,
        sql_executor: SQLExecutor | None = None,
        sql_repairer: SQLRepairer | None = None,
        result_summarizer: ResultSummarizer | None = None,
        memory_manager: Any | None = None,
        schema_service: Any | None = None,
        text_match_sql_builder: TextMatchSQLBuilder | None = None,
        schema_top_k: int = 5,
    ) -> None:
        self.intent_analyzer = intent_analyzer or IntentAnalyzer()
        self.schema_retriever = schema_retriever or SchemaRetriever()
        self.sql_generator = sql_generator or SQLGenerator()
        self.sql_validator = sql_validator or SQLValidator()
        self.sql_executor = sql_executor or SQLExecutor()
        self.sql_repairer = sql_repairer or SQLRepairer(
            validator=self.sql_validator,
            executor=self.sql_executor,
        )
        self.result_summarizer = result_summarizer or ResultSummarizer()
        self.memory_manager = memory_manager
        self.schema_service = schema_service or getattr(self.schema_retriever, "schema_service", None)
        self.text_match_sql_builder = text_match_sql_builder or TextMatchSQLBuilder(self)
        self.schema_top_k = schema_top_k

        if self.schema_top_k <= 0:
            raise ValueError("schema_top_k must be greater than 0")

    def run(self, question: str, session_id: str, selected_table_name: str | None = None) -> dict[str, Any]:
        normalized_question = question.strip()
        normalized_session_id = session_id.strip()
        normalized_selected_table = (selected_table_name or "").strip()

        if not normalized_question:
            raise ValueError("question must not be empty")
        if not normalized_session_id:
            raise ValueError("session_id must not be empty")

        trace: list[TraceEvent | dict[str, Any]] = []
        conversation_context: list[dict[str, Any]] = []
        intent_result: dict[str, Any] | None = None
        schema_context: list[dict[str, Any]] = []
        sql_generation_result: dict[str, Any] | None = None
        validation_result: dict[str, Any] | None = None
        execution_result: dict[str, Any] | None = None
        repair_result: dict[str, Any] | None = None
        summary_result: dict[str, Any] | None = None
        final_sql: str | None = None

        try:
            logger.info(
                "agent.run.start session_id=%s question=%s",
                normalized_session_id,
                sanitize_for_log(normalized_question),
            )
            conversation_context = self._load_conversation_memory(normalized_session_id, trace)

            intent_result = self._run_traced(
                trace=trace,
                step="intent_analysis",
                input_data={
                    "question": normalized_question,
                    "conversation_items": len(conversation_context),
                },
                action=lambda: self.intent_analyzer.analyze(
                    normalized_question,
                    conversation_context=conversation_context,
                ),
                output_mapper=self._intent_trace_output,
            )

            if intent_result.get("requires_clarification"):
                answer = intent_result.get("clarification_question") or "请补充更明确的查询条件。"
                self._append_skipped_after_intent(trace, "Question requires clarification.")
                return self._finalize(
                    session_id=normalized_session_id,
                    question=normalized_question,
                    trace=trace,
                    status="needs_clarification",
                    answer=answer,
                    intent=intent_result,
                    error=None,
                )

            if intent_result.get("intent_type") == "unsupported":
                answer = "这个问题暂时不支持。我只能处理只读的数据查询，不能执行删除、修改或系统操作。"
                self._append_skipped_after_intent(trace, "Unsupported intent.")
                return self._finalize(
                    session_id=normalized_session_id,
                    question=normalized_question,
                    trace=trace,
                    status="unsupported",
                    answer=answer,
                    intent=intent_result,
                    error="Unsupported question type",
                    error_code="unsupported_request",
                )

            retrieval_result = self._run_traced(
                trace=trace,
                step="schema_retrieval",
                input_data={
                    "question": normalized_question,
                    "top_k": self.schema_top_k,
                    "selected_table_name": normalized_selected_table or None,
                    "restrict_to_selected": bool(normalized_selected_table),
                },
                action=lambda: self.schema_retriever.retrieve(
                    normalized_question,
                    top_k=self.schema_top_k,
                    use_keyword_fallback=True,
                    preferred_table_names=[normalized_selected_table] if normalized_selected_table else [],
                    restrict_to_preferred=bool(normalized_selected_table),
                ),
                output_mapper=self._schema_trace_output,
            )
            retrieved_matches = retrieval_result.get("matches") or []
            schema_context = self._enrich_schema_context(retrieved_matches, intent_result)
            if len(schema_context) > len(retrieved_matches):
                append_trace_event(
                    trace=trace,
                    step="schema_context_enrichment",
                    status="success",
                    input_data={
                        "retrieved_tables": [item.get("table_name") for item in retrieved_matches],
                        "intent_tables": (intent_result.get("entities") or {}).get("tables") or [],
                    },
                    output_data={"tables": [item.get("table_name") for item in schema_context]},
                    message="Schema context enriched with intent and relationship tables.",
                )

            sql_generation_result = self._run_traced(
                trace=trace,
                step="sql_generation",
                input_data={
                    "question": normalized_question,
                    "intent_type": intent_result.get("intent_type"),
                    "tables": [item.get("table_name") for item in schema_context],
                },
                action=lambda: self._generate_sql(
                    question=normalized_question,
                    intent_result=intent_result,
                    schema_context=schema_context,
                    conversation_context=conversation_context,
                ),
                output_mapper=self._sql_generation_trace_output,
            )

            generated_sql = sql_generation_result.get("sql")
            if sql_generation_result.get("status") != "success" or not generated_sql:
                generation_error = sql_generation_result.get("explanation") or "SQL generation failed"
                generation_error_info = classify_error(
                    generation_error,
                    status=str(sql_generation_result.get("status") or "failed"),
                    failed_step="sql_generation",
                )
                self._append_skipped_after_sql_generation(trace, "SQL generation did not produce executable SQL.")
                return self._finalize(
                    session_id=normalized_session_id,
                    question=normalized_question,
                    trace=trace,
                    status=str(sql_generation_result.get("status") or "failed"),
                    answer=generation_error_info.message,
                    intent=intent_result,
                    retrieved_schema=schema_context,
                    sql_generation=sql_generation_result,
                    error=generation_error,
                    error_code=generation_error_info.code,
                )

            logger.info(
                "agent.sql.generated session_id=%s sql=%s",
                normalized_session_id,
                sanitize_for_log(generated_sql),
            )
            validation_result = self._run_traced(
                trace=trace,
                step="sql_validation",
                input_data={"sql": generated_sql},
                action=lambda: self.sql_validator.validate(generated_sql, schema_context),
                output_mapper=self._validation_trace_output,
            )

            if not validation_result.get("valid"):
                logger.warning(
                    "agent.sql.validation_failed session_id=%s error=%s sql=%s",
                    normalized_session_id,
                    sanitize_for_log(validation_result.get("error")),
                    sanitize_for_log(generated_sql),
                )
                append_trace_event(
                    trace=trace,
                    step="sql_execution",
                    status="skipped",
                    input_data={"sql": generated_sql},
                    output_data={"reason": validation_result.get("error")},
                    message="SQL validation failed; execution skipped before repair.",
                )
                repair_result = self._run_repair(
                    trace=trace,
                    question=normalized_question,
                    failed_sql=generated_sql,
                    error_message=validation_result.get("error") or "SQL validation failed",
                    schema_context=schema_context,
                    validation_errors=[validation_result.get("error") or "SQL validation failed"],
                )
                if not self._repair_succeeded(repair_result):
                    self._append_skipped_summary(trace, "SQL validation failed and repair did not succeed.")
                    return self._finalize(
                        session_id=normalized_session_id,
                        question=normalized_question,
                        trace=trace,
                        status="failed",
                        answer="SQL 校验失败，无法安全执行查询。",
                        intent=intent_result,
                        retrieved_schema=schema_context,
                        sql_generation=sql_generation_result,
                        validation_result=validation_result,
                        repair_result=repair_result,
                        error=repair_result.get("failure_reason") if repair_result else validation_result.get("error"),
                        error_code="sql_validation_failed",
                    )

                final_sql = repair_result.get("repaired_sql")
                validation_result = repair_result.get("validation_result") or validation_result
                execution_result = repair_result.get("execution_result")
            else:
                execution_result = self._run_traced(
                    trace=trace,
                    step="sql_execution",
                    input_data={"sql": validation_result.get("safe_sql")},
                    action=lambda: self.sql_executor.execute(validation_result),
                    output_mapper=self._execution_trace_output,
                )

                if not execution_result.get("success"):
                    logger.warning(
                        "agent.sql.execution_failed session_id=%s error=%s sql=%s",
                        normalized_session_id,
                        sanitize_for_log(execution_result.get("error")),
                        sanitize_for_log(validation_result.get("safe_sql") or generated_sql),
                    )
                    repair_result = self._run_repair(
                        trace=trace,
                        question=normalized_question,
                        failed_sql=validation_result.get("safe_sql") or generated_sql,
                        error_message=execution_result.get("error") or "SQL execution failed",
                        schema_context=schema_context,
                        validation_errors=[],
                    )
                    if not self._repair_succeeded(repair_result):
                        self._append_skipped_summary(trace, "SQL execution failed and repair did not succeed.")
                        return self._finalize(
                            session_id=normalized_session_id,
                            question=normalized_question,
                            trace=trace,
                            status="failed",
                            answer="查询执行失败，修复后仍无法完成。",
                            intent=intent_result,
                            retrieved_schema=schema_context,
                            sql_generation=sql_generation_result,
                            validation_result=validation_result,
                            execution_result=execution_result,
                            repair_result=repair_result,
                            error=repair_result.get("failure_reason") if repair_result else execution_result.get("error"),
                            error_code="sql_execution_failed",
                        )

                    final_sql = repair_result.get("repaired_sql")
                    validation_result = repair_result.get("validation_result") or validation_result
                    execution_result = repair_result.get("execution_result")
                else:
                    self._append_skipped_repair(trace, "SQL executed successfully.")
                    final_sql = validation_result.get("safe_sql") or generated_sql

            summary_result = self._run_traced(
                trace=trace,
                step="result_summary",
                input_data={
                    "question": normalized_question,
                    "sql": final_sql,
                    "row_count": execution_result.get("row_count") if execution_result else 0,
                },
                action=lambda: self.result_summarizer.summarize(
                    question=normalized_question,
                    sql=final_sql or generated_sql,
                    execution_result=execution_result or {},
                ),
                output_mapper=self._summary_trace_output,
            )

            return self._finalize(
                session_id=normalized_session_id,
                question=normalized_question,
                trace=trace,
                status="success",
                answer=summary_result["answer"],
                sql=final_sql,
                columns=execution_result.get("columns") or [],
                rows=execution_result.get("rows") or [],
                row_count=int(execution_result.get("row_count") or 0),
                intent=intent_result,
                retrieved_schema=schema_context,
                sql_generation=sql_generation_result,
                validation_result=validation_result,
                execution_result=execution_result,
                repair_result=repair_result,
                summary=summary_result,
                error=None,
            )
        except Exception as exc:
            error_info = classify_error(exc, failed_step=failed_step_from_trace(trace))
            logger.error(
                "agent.run.failed session_id=%s error_code=%s error=%s",
                normalized_session_id,
                error_info.code,
                sanitize_for_log(str(exc)),
            )
            return self._finalize(
                session_id=normalized_session_id,
                question=normalized_question,
                trace=trace,
                status="failed",
                answer=error_info.message,
                sql=final_sql,
                intent=intent_result,
                retrieved_schema=schema_context,
                sql_generation=sql_generation_result,
                validation_result=validation_result,
                execution_result=execution_result,
                repair_result=repair_result,
                summary=summary_result,
                error=str(exc),
                error_code=error_info.code,
            )

    def _load_conversation_memory(
        self,
        session_id: str,
        trace: list[TraceEvent | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        started_at = time.perf_counter()
        try:
            context = self._call_memory_load(session_id)
        except Exception as exc:
            logger.warning(
                "agent.memory.load_failed session_id=%s error=%s",
                session_id,
                sanitize_for_log(str(exc)),
            )
            append_trace_event(
                trace=trace,
                step="memory_load",
                status="failed",
                input_data={"session_id": session_id},
                output_data={"error": str(exc)},
                message="Failed to load conversation memory.",
                duration_ms=self._elapsed_ms(started_at),
            )
            return []

        append_trace_event(
            trace=trace,
            step="memory_load",
            status="success" if self.memory_manager is not None else "skipped",
            input_data={"session_id": session_id},
            output_data={"items": len(context), "memory_enabled": self.memory_manager is not None},
            message="Conversation memory loaded." if self.memory_manager is not None else "Conversation memory is not enabled yet.",
            duration_ms=self._elapsed_ms(started_at),
        )
        return context

    def _call_memory_load(self, session_id: str) -> list[dict[str, Any]]:
        if self.memory_manager is None:
            return []
        if hasattr(self.memory_manager, "load"):
            value = self.memory_manager.load(session_id)
        elif hasattr(self.memory_manager, "load_conversation"):
            value = self.memory_manager.load_conversation(session_id)
        else:
            return []

        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("conversation memory must be a list")
        return [self._conversation_memory_item(item) for item in value if isinstance(item, dict)]

    def _conversation_memory_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "question": item.get("question"),
            "answer": item.get("answer"),
            "sql": item.get("sql"),
            "status": item.get("status"),
            "error": item.get("error"),
            "summary": item.get("summary"),
            "resolved_entities": item.get("resolved_entities") or {},
            "retrieved_tables": item.get("retrieved_tables") or [],
            "row_count": item.get("row_count") or 0,
            "created_at": item.get("created_at"),
        }

    def _enrich_schema_context(
        self,
        schema_context: list[dict[str, Any]],
        intent_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        seen_tables: set[str] = set()

        for item in schema_context:
            self._append_schema_context_item(enriched, seen_tables, item)

        candidate_tables = [
            str(table_name)
            for table_name in ((intent_result.get("entities") or {}).get("tables") or [])
            if table_name
        ]
        candidate_tables.extend([item["table_name"] for item in enriched if item.get("table_name")])

        index = 0
        while index < len(candidate_tables):
            table_name = candidate_tables[index]
            index += 1
            if not table_name:
                continue

            table_schema = self._get_table_schema(table_name)
            if table_schema:
                self._append_schema_context_item(
                    enriched,
                    seen_tables,
                    self._schema_context_from_table_schema(table_schema),
                )
                for foreign_key in table_schema.get("foreign_keys", []):
                    referred_table = foreign_key.get("referred_table")
                    if referred_table and referred_table not in candidate_tables:
                        candidate_tables.append(str(referred_table))

        return enriched

    def _generate_sql(
        self,
        question: str,
        intent_result: dict[str, Any],
        schema_context: list[dict[str, Any]],
        conversation_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        text_match_result = self.text_match_sql_builder.build(
            question=question,
            intent_result=intent_result,
            schema_context=schema_context,
        )
        if text_match_result:
            generation_status = text_match_result.get("status") or "success"
            if generation_status != "success":
                return {
                    "status": generation_status,
                    "sql": None,
                    "tables_used": text_match_result.get("tables_used") or [],
                    "columns_used": text_match_result.get("columns_used") or [],
                    "assumptions": text_match_result.get("assumptions") or [],
                    "explanation": text_match_result.get("reason") or "Column mapping needs clarification.",
                    "safety_checks": {
                        "postgresql_dialect": True,
                        "read_only": True,
                        "uses_only_provided_schema": True,
                        "no_invented_tables_or_columns": True,
                    },
                    "source": text_match_result.get("source") or "semantic_match",
                    "raw_response": text_match_result,
                }

            table_name = text_match_result["table_name"]
            return {
                "status": "success",
                "sql": text_match_result["sql"],
                "tables_used": [table_name],
                "columns_used": text_match_result.get("columns_used") or [
                    f"{table_name}.{column}"
                    for column in text_match_result.get("selected_columns", [])
                    if column != "match_score"
                ],
                "assumptions": [
                    text_match_result.get("reason")
                    or "Text lookup questions are matched against textual columns with a minimum keyword score.",
                ],
                "explanation": text_match_result["reason"],
                "safety_checks": {
                    "postgresql_dialect": True,
                    "read_only": True,
                    "uses_only_provided_schema": True,
                    "no_invented_tables_or_columns": True,
                },
                "source": text_match_result["source"],
                "raw_response": text_match_result,
            }

        return self.sql_generator.generate(
            question=question,
            intent_result=intent_result,
            schema_context=schema_context,
            conversation_context=conversation_context,
        )

    def _append_schema_context_item(
        self,
        context: list[dict[str, Any]],
        seen_tables: set[str],
        item: dict[str, Any],
    ) -> None:
        table_name = item.get("table_name") or item.get("name")
        if not table_name or table_name in seen_tables:
            return

        normalized_item = dict(item)
        normalized_item["table_name"] = str(table_name)
        if "columns" not in normalized_item:
            normalized_item["columns"] = []
        context.append(normalized_item)
        seen_tables.add(str(table_name))

    def _get_table_schema(self, table_name: str) -> dict[str, Any]:
        try:
            service = self._get_schema_service()
            if service is None:
                return {}
            return service.get_table_schema(table_name) or {}
        except Exception:
            return {}

    def _get_schema_service(self):
        if self.schema_service is None:
            from app.services.schema_service import SchemaService

            self.schema_service = SchemaService()
        return self.schema_service

    def _schema_context_from_table_schema(self, table_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "table_name": table_schema["name"],
            "columns": [column["name"] for column in table_schema.get("columns", [])],
            "content": table_schema.get("description", ""),
        }

    def _save_conversation_memory(
        self,
        session_id: str,
        question: str,
        result: dict[str, Any],
        trace: list[TraceEvent | dict[str, Any]],
    ) -> None:
        started_at = time.perf_counter()
        if self.memory_manager is None:
            append_trace_event(
                trace=trace,
                step="memory_save",
                status="skipped",
                input_data={"session_id": session_id},
                output_data={"memory_enabled": False},
                message="Conversation memory is not enabled yet.",
                duration_ms=self._elapsed_ms(started_at),
            )
            return

        record = {
            "question": question,
            "answer": result.get("answer"),
            "sql": result.get("sql"),
            "status": result.get("status"),
            "error": result.get("error"),
            "summary": result.get("summary"),
            "resolved_entities": (result.get("intent") or {}).get("entities") or {},
            "retrieved_tables": [item.get("table_name") for item in result.get("retrieved_schema", [])],
            "columns": result.get("columns") or [],
            "rows": result.get("rows") or [],
            "row_count": result.get("row_count") or 0,
        }
        try:
            if hasattr(self.memory_manager, "save"):
                self.memory_manager.save(session_id, record)
            elif hasattr(self.memory_manager, "save_conversation"):
                self.memory_manager.save_conversation(session_id, record)
            append_trace_event(
                trace=trace,
                step="memory_save",
                status="success",
                input_data={"session_id": session_id, "record": record},
                output_data={"saved": True},
                message="Conversation memory saved.",
                duration_ms=self._elapsed_ms(started_at),
            )
        except Exception as exc:
            logger.warning(
                "agent.memory.save_failed session_id=%s error=%s",
                session_id,
                sanitize_for_log(str(exc)),
            )
            append_trace_event(
                trace=trace,
                step="memory_save",
                status="failed",
                input_data={"session_id": session_id},
                output_data={"error": str(exc)},
                message="Failed to save conversation memory.",
                duration_ms=self._elapsed_ms(started_at),
            )

    def _run_traced(
        self,
        trace: list[TraceEvent | dict[str, Any]],
        step: str,
        input_data: dict[str, Any],
        action,
        output_mapper,
    ):
        started_at = time.perf_counter()
        logger.info(
            "agent.step.start step=%s input=%s",
            step,
            sanitize_for_log(input_data),
        )
        try:
            result = action()
        except Exception as exc:
            duration_ms = self._elapsed_ms(started_at)
            append_trace_event(
                trace=trace,
                step=step,
                status="failed",
                input_data=input_data,
                output_data={"error": str(exc)},
                message=f"{step} failed.",
                duration_ms=duration_ms,
            )
            logger.error(
                "agent.step.failed step=%s duration_ms=%s error=%s",
                step,
                duration_ms,
                sanitize_for_log(str(exc)),
            )
            raise

        output = output_mapper(result)
        status = self._trace_status_from_output(step, output)
        duration_ms = self._elapsed_ms(started_at)
        append_trace_event(
            trace=trace,
            step=step,
            status=status,
            input_data=input_data,
            output_data=output,
            message=f"{step} completed." if status == "success" else f"{step} returned a failure result.",
            duration_ms=duration_ms,
        )
        logger.info(
            "agent.step.end step=%s status=%s duration_ms=%s output=%s",
            step,
            status,
            duration_ms,
            sanitize_for_log(output),
        )
        return result

    def _run_repair(
        self,
        trace: list[TraceEvent | dict[str, Any]],
        question: str,
        failed_sql: str,
        error_message: str,
        schema_context: list[dict[str, Any]],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        return self._run_traced(
            trace=trace,
            step="sql_repair",
            input_data={
                "question": question,
                "failed_sql": failed_sql,
                "error_message": error_message,
            },
            action=lambda: self.sql_repairer.repair(
                question=question,
                failed_sql=failed_sql,
                error_message=error_message,
                schema_context=schema_context,
                validation_errors=validation_errors,
            ),
            output_mapper=self._repair_trace_output,
        )

    def _finalize(
        self,
        session_id: str,
        question: str,
        trace: list[TraceEvent | dict[str, Any]],
        status: str,
        answer: str,
        sql: str | None = None,
        columns: list[str] | None = None,
        rows: list[dict[str, Any]] | None = None,
        row_count: int = 0,
        retrieved_schema: list[dict[str, Any]] | None = None,
        intent: dict[str, Any] | None = None,
        sql_generation: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
        repair_result: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        normalized_answer = answer
        normalized_error = error
        normalized_error_code = error_code
        if error:
            error_info = classify_error(
                error,
                status=status,
                failed_step=failed_step_from_trace(trace),
                default_code=error_code or "internal_error",
            )
            normalized_error = error_info.message
            normalized_error_code = error_info.code
            if self._answer_should_use_error_message(answer):
                normalized_answer = error_info.message

        result = Text2SQLAgentResult(
            status=status,
            answer=normalized_answer,
            session_id=session_id,
            sql=sql,
            columns=columns or [],
            rows=rows or [],
            row_count=row_count,
            retrieved_schema=retrieved_schema or [],
            trace=[],
            intent=intent,
            sql_generation=sql_generation,
            validation_result=validation_result,
            execution_result=execution_result,
            repair_result=repair_result,
            summary=summary,
            error=normalized_error,
            error_code=normalized_error_code,
        ).to_dict()

        self._save_conversation_memory(session_id, question, result, trace)
        result["trace"] = trace_events_to_dicts(trace)
        logger.info(
            "agent.run.end session_id=%s status=%s error_code=%s row_count=%s",
            session_id,
            result.get("status"),
            result.get("error_code"),
            result.get("row_count"),
        )
        return result

    def _append_skipped_after_intent(self, trace: list[TraceEvent | dict[str, Any]], reason: str) -> None:
        for step in [
            "schema_retrieval",
            "sql_generation",
            "sql_validation",
            "sql_execution",
            "sql_repair",
            "result_summary",
        ]:
            append_trace_event(trace, step=step, status="skipped", message=reason)

    def _append_skipped_after_sql_generation(self, trace: list[TraceEvent | dict[str, Any]], reason: str) -> None:
        for step in ["sql_validation", "sql_execution", "sql_repair", "result_summary"]:
            append_trace_event(trace, step=step, status="skipped", message=reason)

    def _append_skipped_summary(self, trace: list[TraceEvent | dict[str, Any]], reason: str) -> None:
        append_trace_event(trace, step="result_summary", status="skipped", message=reason)

    def _append_skipped_repair(self, trace: list[TraceEvent | dict[str, Any]], reason: str) -> None:
        append_trace_event(trace, step="sql_repair", status="skipped", message=reason)

    def _answer_should_use_error_message(self, answer: str) -> bool:
        lowered = answer.lower()
        technical_terms = [
            "agent pipeline failed",
            "sql generation failed",
            "llm_",
            "traceback",
            "exception",
            "valid json",
            "invalid json",
            "provider request",
            "psycopg",
            "sqlalchemy",
        ]
        return any(term in lowered for term in technical_terms)

    def _repair_succeeded(self, repair_result: dict[str, Any] | None) -> bool:
        return bool(
            repair_result
            and repair_result.get("status") == "repaired"
            and repair_result.get("repaired_sql")
            and (repair_result.get("execution_result") or {}).get("success")
        )

    def _trace_status_from_output(self, step: str, output: dict[str, Any]) -> str:
        if output.get("valid") is False or output.get("success") is False:
            return "failed"
        if step == "sql_generation" and output.get("status") not in {None, "success"}:
            return "failed"
        if step == "sql_repair" and output.get("status") != "repaired":
            return "failed"
        return "success"

    def _intent_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        entities = result.get("entities") or {}
        return {
            "intent_type": result.get("intent_type"),
            "confidence": result.get("confidence"),
            "requires_clarification": result.get("requires_clarification"),
            "tables": entities.get("tables") or [],
            "source": result.get("source"),
        }

    def _schema_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        matches = result.get("matches") or []
        return {
            "matches": len(matches),
            "tables": [match.get("table_name") for match in matches],
            "sources": [match.get("source") for match in matches],
        }

    def _sql_generation_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("status"),
            "sql": result.get("sql"),
            "tables_used": result.get("tables_used") or [],
            "source": result.get("source"),
            "explanation": result.get("explanation"),
        }

    def _validation_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "valid": result.get("valid"),
            "safe_sql": result.get("safe_sql"),
            "error": result.get("error"),
            "referenced_tables": result.get("referenced_tables") or [],
            "limit_applied": result.get("limit_applied"),
        }

    def _execution_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": result.get("success"),
            "row_count": result.get("row_count"),
            "columns": result.get("columns") or [],
            "truncated": result.get("truncated"),
            "error": result.get("error"),
        }

    def _repair_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("status"),
            "repaired_sql": result.get("repaired_sql"),
            "failure_reason": result.get("failure_reason"),
            "attempts": [attempt.get("status") for attempt in result.get("attempts", [])],
        }

    def _summary_trace_output(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "answer": result.get("answer"),
            "row_count": result.get("row_count"),
            "source": result.get("source"),
        }

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 3)
