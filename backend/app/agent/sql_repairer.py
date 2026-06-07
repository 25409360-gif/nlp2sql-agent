from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.prompts.sql_repair_prompt import build_sql_repair_prompt
from app.agent.sql_executor import SQLExecutor
from app.agent.sql_validator import SQLValidator
from app.services.llm_client import LLMClient, LLMProviderError, create_llm_client


SQL_REPAIR_STATUSES = {"repaired", "unrepairable"}


@dataclass
class SQLRepairAttempt:
    attempt: int
    status: str
    repaired_sql: str | None = None
    validation_error: str | None = None
    execution_error: str | None = None
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SQLRepairResult:
    status: str
    repaired_sql: str | None
    failure_reason: str | None = None
    changes: list[str] = field(default_factory=list)
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    explanation: str = ""
    validation_result: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    source: str = "llm"
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLRepairer:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        validator: SQLValidator | None = None,
        executor: SQLExecutor | None = None,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than 0")

        self.llm_client = llm_client or create_llm_client()
        self.validator = validator or SQLValidator()
        self.executor = executor or SQLExecutor()
        self.max_attempts = max_attempts

    def repair(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        schema_context: list[dict[str, Any]],
        validation_errors: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_question = question.strip()
        normalized_sql = failed_sql.strip()
        normalized_error = error_message.strip()

        if not normalized_question:
            raise ValueError("question must not be empty")
        if not normalized_sql:
            raise ValueError("failed_sql must not be empty")
        if not normalized_error:
            raise ValueError("error_message must not be empty")

        attempts: list[dict[str, Any]] = []
        accumulated_errors = [str(item) for item in (validation_errors or []) if item]
        current_sql = normalized_sql
        current_error = normalized_error
        last_failure = normalized_error

        for attempt_number in range(1, self.max_attempts + 1):
            try:
                raw_response = self._request_repair(
                    question=normalized_question,
                    failed_sql=current_sql,
                    error_message=current_error,
                    schema_context=schema_context,
                    validation_errors=accumulated_errors,
                )
                repair_response = self._normalize_repair_response(raw_response)
            except Exception as exc:
                last_failure = f"SQL repair LLM call failed: {exc}"
                attempts.append(
                    SQLRepairAttempt(
                        attempt=attempt_number,
                        status="llm_failed",
                        validation_error=last_failure,
                    ).to_dict()
                )
                break

            if repair_response["status"] == "unrepairable":
                explanation = repair_response["explanation"] or "SQL cannot be repaired safely."
                attempts.append(
                    SQLRepairAttempt(
                        attempt=attempt_number,
                        status="unrepairable",
                        explanation=explanation,
                    ).to_dict()
                )
                return SQLRepairResult(
                    status="unrepairable",
                    repaired_sql=None,
                    failure_reason=explanation,
                    changes=repair_response["changes"],
                    tables_used=repair_response["tables_used"],
                    columns_used=repair_response["columns_used"],
                    explanation=explanation,
                    attempts=attempts,
                    raw_response=raw_response,
                ).to_dict()

            repaired_sql = repair_response["repaired_sql"]
            validation_result = self.validator.validate(repaired_sql, schema_context)
            if not validation_result.get("valid"):
                last_failure = validation_result.get("error") or "Repaired SQL did not pass validation"
                accumulated_errors.append(last_failure)
                attempts.append(
                    SQLRepairAttempt(
                        attempt=attempt_number,
                        status="validation_failed",
                        repaired_sql=repaired_sql,
                        validation_error=last_failure,
                        explanation=repair_response["explanation"],
                    ).to_dict()
                )
                current_sql = repaired_sql
                current_error = last_failure
                continue

            execution_result = self.executor.execute(validation_result)
            if not execution_result.get("success"):
                last_failure = execution_result.get("error") or "Repaired SQL failed during execution"
                accumulated_errors.append(last_failure)
                attempts.append(
                    SQLRepairAttempt(
                        attempt=attempt_number,
                        status="execution_failed",
                        repaired_sql=validation_result.get("safe_sql") or repaired_sql,
                        execution_error=last_failure,
                        explanation=repair_response["explanation"],
                    ).to_dict()
                )
                current_sql = validation_result.get("safe_sql") or repaired_sql
                current_error = last_failure
                continue

            safe_sql = validation_result.get("safe_sql") or repaired_sql
            attempts.append(
                SQLRepairAttempt(
                    attempt=attempt_number,
                    status="repaired",
                    repaired_sql=safe_sql,
                    explanation=repair_response["explanation"],
                ).to_dict()
            )
            return SQLRepairResult(
                status="repaired",
                repaired_sql=safe_sql,
                failure_reason=None,
                changes=repair_response["changes"],
                tables_used=repair_response["tables_used"],
                columns_used=repair_response["columns_used"],
                explanation=repair_response["explanation"],
                validation_result=validation_result,
                execution_result=execution_result,
                attempts=attempts,
                raw_response=raw_response,
            ).to_dict()

        return SQLRepairResult(
            status="failed",
            repaired_sql=None,
            failure_reason=f"SQL repair failed after {self.max_attempts} attempt(s): {last_failure}",
            attempts=attempts,
            source="fallback",
        ).to_dict()

    def _request_repair(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        schema_context: list[dict[str, Any]],
        validation_errors: list[str],
    ) -> dict[str, Any]:
        prompt = build_sql_repair_prompt(
            question=question,
            failed_sql=failed_sql,
            error_message=error_message,
            schema_context=schema_context,
            validation_errors=validation_errors,
        )

        response = self._call_llm(prompt)
        parsed = response.parsed_json
        if parsed is None:
            parsed = self.llm_client.extract_json(response.content)
        if not isinstance(parsed, dict):
            raise ValueError("SQL repair response must be a JSON object")
        return parsed

    def _call_llm(self, prompt: dict[str, str]):
        try:
            return self.llm_client.chat_completion(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                json_mode=True,
                temperature=0.0,
            )
        except LLMProviderError:
            return self.llm_client.chat_completion(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                json_mode=False,
                temperature=0.0,
            )

    def _normalize_repair_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        status = str(raw.get("status") or "").strip()
        if status not in SQL_REPAIR_STATUSES:
            raise ValueError(f"unsupported SQL repair status: {status}")

        repaired_sql = self._optional_string(raw.get("repaired_sql"))
        if status == "repaired" and not repaired_sql:
            raise ValueError("repaired SQL response must include repaired_sql")
        if status == "unrepairable":
            repaired_sql = None

        return {
            "status": status,
            "repaired_sql": repaired_sql,
            "changes": self._string_list(raw.get("changes")),
            "tables_used": self._string_list(raw.get("tables_used")),
            "columns_used": self._string_list(raw.get("columns_used")),
            "explanation": str(raw.get("explanation") or ""),
        }

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]
