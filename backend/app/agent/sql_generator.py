import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.prompts.sql_generation_prompt import build_sql_generation_prompt
from app.services.llm_client import LLMClient, LLMProviderError, create_llm_client


SQL_GENERATION_STATUSES = {"success", "needs_clarification", "unsupported"}
FORBIDDEN_SQL_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "execute",
    "exec",
}


@dataclass
class SQLGenerationResult:
    status: str
    sql: str | None
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    explanation: str = ""
    safety_checks: dict[str, bool] = field(default_factory=dict)
    source: str = "llm"
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLGenerator:
    def __init__(self, llm_client: LLMClient | None = None, schema_service: Any | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()
        self.schema_service = schema_service

    def generate(
        self,
        question: str,
        intent_result: dict[str, Any],
        schema_context: list[dict[str, Any]],
        conversation_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        enriched_schema_context = self._enrich_schema_context(schema_context, intent_result)
        prompt = build_sql_generation_prompt(
            question=normalized_question,
            intent=intent_result,
            schema_context=enriched_schema_context,
            conversation_context=conversation_context or [],
        )

        try:
            response = self._call_llm(prompt)
            parsed = response.parsed_json
            if parsed is None:
                parsed = self.llm_client.extract_json(response.content)
            return self._normalize_result(parsed, enriched_schema_context).to_dict()
        except Exception as exc:
            return SQLGenerationResult(
                status="needs_clarification",
                sql=None,
                explanation=f"SQL generation failed or returned invalid JSON: {exc}",
                safety_checks=self._empty_safety_checks(),
                source="fallback",
                raw_response=None,
            ).to_dict()

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

    def _normalize_result(
        self,
        raw: Any,
        schema_context: list[dict[str, Any]],
    ) -> SQLGenerationResult:
        if not isinstance(raw, dict):
            raise ValueError("SQL generation response must be a JSON object")

        status = str(raw.get("status") or "").strip()
        if status not in SQL_GENERATION_STATUSES:
            raise ValueError(f"unsupported SQL generation status: {status}")

        sql = self._optional_string(raw.get("sql"))
        tables_used = self._string_list(raw.get("tables_used"))
        columns_used = self._string_list(raw.get("columns_used"))
        assumptions = self._string_list(raw.get("assumptions"))
        explanation = str(raw.get("explanation") or "")

        safety_checks = self._compute_safety_checks(sql, schema_context)
        tables_used = self._normalize_tables(tables_used, schema_context)
        columns_used = self._normalize_columns(columns_used, schema_context)

        if status == "success" and not self._all_safety_checks_pass(safety_checks):
            return SQLGenerationResult(
                status="needs_clarification",
                sql=None,
                tables_used=tables_used,
                columns_used=columns_used,
                assumptions=assumptions,
                explanation="Generated SQL failed local safety checks and was not accepted.",
                safety_checks=safety_checks,
                source="llm_rejected",
                raw_response=raw,
            )

        if status == "success" and not sql:
            raise ValueError("successful SQL generation must include sql")

        if status != "success":
            sql = None

        return SQLGenerationResult(
            status=status,
            sql=sql,
            tables_used=tables_used,
            columns_used=columns_used,
            assumptions=assumptions,
            explanation=explanation,
            safety_checks=safety_checks,
            source="llm",
            raw_response=raw,
        )

    def _enrich_schema_context(
        self,
        schema_context: list[dict[str, Any]],
        intent_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        seen_tables: set[str] = set()

        for item in schema_context:
            self._append_schema_context_item(enriched, seen_tables, item)

        candidate_tables = self._string_list((intent_result.get("entities") or {}).get("tables"))
        for table_name in list(seen_tables):
            table_schema = self._get_table_schema(table_name)
            for foreign_key in table_schema.get("foreign_keys", []):
                referred_table = foreign_key.get("referred_table")
                if referred_table:
                    candidate_tables.append(str(referred_table))

        for table_name in candidate_tables:
            if table_name in seen_tables:
                continue
            table_schema = self._get_table_schema(table_name)
            if table_schema:
                self._append_schema_context_item(
                    enriched,
                    seen_tables,
                    self._schema_context_from_table_schema(table_schema),
                )

        return enriched

    def _append_schema_context_item(
        self,
        context: list[dict[str, Any]],
        seen_tables: set[str],
        item: dict[str, Any],
    ) -> None:
        table_name = item.get("table_name")
        if not table_name or table_name in seen_tables:
            return
        context.append(item)
        seen_tables.add(str(table_name))

    def _get_table_schema(self, table_name: str) -> dict[str, Any]:
        try:
            service = self._get_schema_service()
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

    def _compute_safety_checks(
        self,
        sql: str | None,
        schema_context: list[dict[str, Any]],
    ) -> dict[str, bool]:
        if not sql:
            return self._empty_safety_checks()

        read_only = self._is_read_only_sql(sql)
        tables_ok = self._sql_uses_only_known_tables(sql, schema_context)
        columns_ok = self._sql_uses_only_known_columns(sql, schema_context)
        return {
            "postgresql_dialect": True,
            "read_only": read_only,
            "uses_only_provided_schema": tables_ok and columns_ok,
            "no_invented_tables_or_columns": tables_ok and columns_ok,
        }

    def _is_read_only_sql(self, sql: str) -> bool:
        normalized = sql.strip().lower()
        if not (normalized.startswith("select") or normalized.startswith("with")):
            return False
        if ";" in normalized.rstrip(";"):
            return False
        tokens = set(re.findall(r"[a-z_]+", normalized))
        return not bool(tokens & FORBIDDEN_SQL_KEYWORDS)

    def _sql_uses_only_known_tables(self, sql: str, schema_context: list[dict[str, Any]]) -> bool:
        allowed_tables = set(self._allowed_tables(schema_context))
        referenced_tables = set(self._referenced_tables(sql))
        return bool(referenced_tables) and referenced_tables <= allowed_tables

    def _sql_uses_only_known_columns(self, sql: str, schema_context: list[dict[str, Any]]) -> bool:
        allowed_columns = self._allowed_columns_by_table(schema_context)
        alias_to_table = self._alias_to_table(sql)

        for qualifier, column in re.findall(r"\b([a-zA-Z_][\w]*)\.([a-zA-Z_][\w]*)\b", sql):
            table_name = alias_to_table.get(qualifier, qualifier)
            if table_name not in allowed_columns:
                return False
            if column not in allowed_columns[table_name]:
                return False

        return True

    def _referenced_tables(self, sql: str) -> list[str]:
        tables = []
        for match in re.finditer(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", sql, flags=re.IGNORECASE):
            table_name = match.group(1).split(".")[-1]
            tables.append(table_name)
        return tables

    def _alias_to_table(self, sql: str) -> dict[str, str]:
        aliases = {}
        pattern = re.compile(
            r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)(?:\s+(?:as\s+)?([a-zA-Z_][\w]*))?",
            flags=re.IGNORECASE,
        )
        reserved = {"on", "where", "group", "order", "limit", "left", "right", "inner", "outer", "full", "join"}
        for match in pattern.finditer(sql):
            table_name = match.group(1).split(".")[-1]
            alias = match.group(2)
            aliases[table_name] = table_name
            if alias and alias.lower() not in reserved:
                aliases[alias] = table_name
        return aliases

    def _normalize_tables(self, tables: list[str], schema_context: list[dict[str, Any]]) -> list[str]:
        allowed_tables = set(self._allowed_tables(schema_context))
        return [table for table in self._unique(tables) if table in allowed_tables]

    def _normalize_columns(self, columns: list[str], schema_context: list[dict[str, Any]]) -> list[str]:
        allowed_columns = self._allowed_columns_by_table(schema_context)
        normalized = []
        for column_ref in self._unique(columns):
            if "." not in column_ref:
                continue
            table_name, column_name = column_ref.split(".", maxsplit=1)
            if table_name in allowed_columns and column_name in allowed_columns[table_name]:
                normalized.append(column_ref)
        return normalized

    def _allowed_tables(self, schema_context: list[dict[str, Any]]) -> list[str]:
        return [str(item["table_name"]) for item in schema_context if item.get("table_name")]

    def _allowed_columns_by_table(self, schema_context: list[dict[str, Any]]) -> dict[str, set[str]]:
        columns_by_table = {}
        for item in schema_context:
            table_name = item.get("table_name")
            if not table_name:
                continue
            columns_by_table[str(table_name)] = {str(column) for column in item.get("columns", [])}
        return columns_by_table

    def _all_safety_checks_pass(self, safety_checks: dict[str, bool]) -> bool:
        return all(safety_checks.values())

    def _empty_safety_checks(self) -> dict[str, bool]:
        return {
            "postgresql_dialect": True,
            "read_only": False,
            "uses_only_provided_schema": False,
            "no_invented_tables_or_columns": False,
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

    def _unique(self, values: list[str]) -> list[str]:
        unique_values = []
        for value in values:
            if value not in unique_values:
                unique_values.append(value)
        return unique_values
