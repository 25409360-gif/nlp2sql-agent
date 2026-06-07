import re
from dataclasses import asdict, dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from app.core.config import settings


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

SENSITIVE_COLUMNS = {
    "password",
    "password_hash",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "private_key",
    "ssn",
}


@dataclass
class SQLValidationResult:
    valid: bool
    safe_sql: str | None
    original_sql: str
    referenced_tables: list[str] = field(default_factory=list)
    referenced_columns: list[str] = field(default_factory=list)
    error: str | None = None
    limit_applied: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLValidator:
    def __init__(
        self,
        default_limit: int | None = None,
        max_limit: int | None = None,
        schema_service: Any | None = None,
    ) -> None:
        self.default_limit = default_limit or settings.sql_default_limit
        self.max_limit = max_limit or settings.sql_max_limit
        self.schema_service = schema_service

        if self.default_limit <= 0:
            raise ValueError("default SQL limit must be greater than 0")
        if self.max_limit <= 0:
            raise ValueError("max SQL limit must be greater than 0")
        if self.default_limit > self.max_limit:
            raise ValueError("default SQL limit must be less than or equal to max SQL limit")

    def validate(
        self,
        sql: str,
        schema_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        original_sql = sql or ""
        if not original_sql.strip():
            return self._invalid(original_sql, "SQL is empty")

        try:
            expressions = sqlglot.parse(original_sql, read="postgres")
        except sqlglot.errors.ParseError as exc:
            return self._invalid(original_sql, f"SQL parse error: {exc}")

        if len(expressions) != 1:
            return self._invalid(original_sql, "Only one SQL statement is allowed")

        expression = expressions[0]
        if not isinstance(expression, exp.Select):
            return self._invalid(original_sql, "Only SELECT statements are allowed")

        if self._contains_forbidden_keyword(original_sql) or self._contains_mutation_expression(expression):
            return self._invalid(original_sql, "Mutation or unsafe SQL statement is not allowed")

        schema_lookup = self._schema_lookup(schema_context)
        referenced_tables = self._referenced_tables(expression)
        if schema_lookup and not set(referenced_tables) <= set(schema_lookup):
            unknown = sorted(set(referenced_tables) - set(schema_lookup))
            return self._invalid(original_sql, f"Unknown table(s): {', '.join(unknown)}", referenced_tables)

        column_result = self._referenced_columns(expression, schema_lookup, referenced_tables)
        if column_result["error"]:
            return self._invalid(original_sql, column_result["error"], referenced_tables, column_result["columns"])

        sensitive = sorted({column.split(".")[-1] for column in column_result["columns"]} & SENSITIVE_COLUMNS)
        if sensitive:
            return self._invalid(
                original_sql,
                f"Sensitive column(s) are not allowed: {', '.join(sensitive)}",
                referenced_tables,
                column_result["columns"],
            )

        safe_sql, limit_applied = self._enforce_limit(original_sql)
        return SQLValidationResult(
            valid=True,
            safe_sql=safe_sql,
            original_sql=original_sql,
            referenced_tables=referenced_tables,
            referenced_columns=column_result["columns"],
            error=None,
            limit_applied=limit_applied,
        ).to_dict()

    def _schema_lookup(self, schema_context: list[dict[str, Any]] | None) -> dict[str, set[str]]:
        if schema_context is None:
            schema_context = self._load_schema_context()

        lookup = {}
        for table in schema_context or []:
            table_name = table.get("table_name") or table.get("name")
            if not table_name:
                continue
            lookup[str(table_name)] = {str(column) for column in table.get("columns", [])}
        return lookup

    def _load_schema_context(self) -> list[dict[str, Any]]:
        try:
            service = self._get_schema_service()
            return [
                {
                    "table_name": table["name"],
                    "columns": [column["name"] for column in table.get("columns", [])],
                }
                for table in service.get_metadata()
            ]
        except Exception:
            return []

    def _get_schema_service(self):
        if self.schema_service is None:
            from app.services.schema_service import SchemaService

            self.schema_service = SchemaService()
        return self.schema_service

    def _contains_forbidden_keyword(self, sql: str) -> bool:
        tokens = set(re.findall(r"[a-z_]+", sql.lower()))
        return bool(tokens & FORBIDDEN_SQL_KEYWORDS)

    def _contains_mutation_expression(self, expression: exp.Expression) -> bool:
        mutation_types = (
            exp.Insert,
            exp.Update,
            exp.Delete,
            exp.Drop,
            exp.Create,
            exp.Alter,
        )
        return any(isinstance(node, mutation_types) for node in expression.walk())

    def _referenced_tables(self, expression: exp.Expression) -> list[str]:
        tables = []
        cte_names = {cte.alias for cte in expression.find_all(exp.CTE) if cte.alias}
        for table in expression.find_all(exp.Table):
            table_name = table.name
            if table_name and table_name not in cte_names and table_name not in tables:
                tables.append(table_name)
        return tables

    def _referenced_columns(
        self,
        expression: exp.Expression,
        schema_lookup: dict[str, set[str]],
        referenced_tables: list[str],
    ) -> dict[str, Any]:
        columns = []
        alias_to_table = self._alias_to_table(expression)
        select_aliases = self._select_aliases(expression)

        for column in expression.find_all(exp.Column):
            column_name = column.name
            if not column_name or column_name == "*":
                continue
            if column_name in select_aliases and not column.table:
                continue

            table_name = alias_to_table.get(column.table, column.table) if column.table else None
            if table_name:
                column_ref = f"{table_name}.{column_name}"
                if schema_lookup and (table_name not in schema_lookup or column_name not in schema_lookup[table_name]):
                    return {"columns": columns, "error": f"Unknown column: {column_ref}"}
                if column_ref not in columns:
                    columns.append(column_ref)
                continue

            possible_tables = [
                table
                for table in referenced_tables
                if table in schema_lookup and column_name in schema_lookup[table]
            ]
            if schema_lookup and not possible_tables:
                return {"columns": columns, "error": f"Unknown column: {column_name}"}
            if len(possible_tables) > 1:
                return {"columns": columns, "error": f"Ambiguous unqualified column: {column_name}"}
            if possible_tables:
                column_ref = f"{possible_tables[0]}.{column_name}"
                if column_ref not in columns:
                    columns.append(column_ref)

        return {"columns": columns, "error": None}

    def _alias_to_table(self, expression: exp.Expression) -> dict[str, str]:
        aliases = {}
        for table in expression.find_all(exp.Table):
            table_name = table.name
            if not table_name:
                continue
            aliases[table_name] = table_name
            alias = table.alias
            if alias:
                aliases[alias] = table_name
        return aliases

    def _select_aliases(self, expression: exp.Expression) -> set[str]:
        aliases = set()
        for select_expression in expression.expressions:
            alias = select_expression.alias
            if alias:
                aliases.add(alias)
        return aliases

    def _enforce_limit(self, sql: str) -> tuple[str, int]:
        sql_without_semicolon = sql.strip().rstrip(";")
        limit_match = list(re.finditer(r"\blimit\s+(\d+)\b", sql_without_semicolon, flags=re.IGNORECASE))
        if not limit_match:
            return f"{sql_without_semicolon} LIMIT {self.default_limit}", self.default_limit

        last_match = limit_match[-1]
        requested_limit = int(last_match.group(1))
        applied_limit = min(requested_limit, self.max_limit)
        if requested_limit <= self.max_limit:
            return sql_without_semicolon, requested_limit

        safe_sql = (
            f"{sql_without_semicolon[: last_match.start()]}"
            f"LIMIT {applied_limit}"
            f"{sql_without_semicolon[last_match.end():]}"
        )
        return safe_sql, applied_limit

    def _invalid(
        self,
        sql: str,
        error: str,
        referenced_tables: list[str] | None = None,
        referenced_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        return SQLValidationResult(
            valid=False,
            safe_sql=None,
            original_sql=sql,
            referenced_tables=referenced_tables or [],
            referenced_columns=referenced_columns or [],
            error=error,
            limit_applied=None,
        ).to_dict()
