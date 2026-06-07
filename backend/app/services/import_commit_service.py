from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings
from app.services.import_preview_service import ImportPreviewService
from app.services.table_data_safety import (
    normalize_identifier,
    qualified_table_name,
    quote_identifier,
)


POSTGRES_TYPE_BY_IMPORT_TYPE = {
    "text": "TEXT",
    "integer": "BIGINT",
    "numeric": "NUMERIC",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
}


class ImportCommitError(ValueError):
    pass


class DuplicateImportTableError(ImportCommitError):
    pass


class EmptyImportDataError(ImportCommitError):
    pass


class ImportCommitService:
    def __init__(
        self,
        preview_service: ImportPreviewService | None = None,
        schema_refresh_service: Any | None = None,
        db_engine: Any | None = None,
        schema_name: str | None = None,
        sql_text_factory: Any | None = None,
    ) -> None:
        self.preview_service = preview_service
        self.schema_refresh_service = schema_refresh_service
        self.db_engine = db_engine
        self.schema_name = schema_name or settings.db_schema
        self.sql_text_factory = sql_text_factory

    def commit_file(
        self,
        *,
        table_name: str,
        filename: str,
        content: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        safe_table_name = normalize_identifier(table_name, field_name="table_name")
        safe_schema_name = normalize_identifier(self.schema_name, field_name="schema_name")
        preview = self._preview_service().preview_file(
            filename=filename,
            content=content,
            content_type=content_type,
            preview_limit=None,
        )
        columns = self._normalized_columns(preview.get("columns") or [])
        rows = preview.get("rows") or []
        if not columns:
            raise EmptyImportDataError("文件中没有有效字段。")
        if not rows:
            raise EmptyImportDataError("文件中没有可导入的数据行。")

        prepared_rows = [_prepare_insert_row(row, columns) for row in rows]
        with self._engine().begin() as connection:
            if self._table_exists(connection, safe_schema_name, safe_table_name):
                raise DuplicateImportTableError(f"数据表已存在：{safe_table_name}")

            connection.execute(self._sql_text(_build_create_table_sql(safe_schema_name, safe_table_name, columns)))
            self._apply_comments(connection, safe_schema_name, safe_table_name, filename, columns)
            connection.execute(
                self._sql_text(_build_insert_sql(safe_schema_name, safe_table_name, columns)),
                prepared_rows,
            )

        schema_refresh = self._schema_refresh_service().refresh_after_import(safe_table_name)
        return {
            "filename": preview.get("filename") or filename,
            "extension": preview.get("extension") or "",
            "schema_name": safe_schema_name,
            "table_name": safe_table_name,
            "columns": columns,
            "row_count": len(prepared_rows),
            "column_count": len(columns),
            "created": True,
            "warnings": preview.get("warnings") or [],
            "schema_refresh": schema_refresh,
        }

    def _normalized_columns(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_columns = []
        used_names: set[str] = set()
        for column in columns:
            name = normalize_identifier(str(column.get("name") or ""), field_name="column_name")
            if name in used_names:
                raise ImportCommitError(f"字段名重复：{name}")
            used_names.add(name)

            import_type = str(column.get("type") or "text")
            if import_type not in POSTGRES_TYPE_BY_IMPORT_TYPE:
                import_type = "text"

            normalized_columns.append(
                {
                    "name": name,
                    "original_name": str(column.get("original_name") or name),
                    "type": import_type,
                    "nullable": bool(column.get("nullable", True)),
                    "sample_values": list(column.get("sample_values") or []),
                }
            )
        return normalized_columns

    def _table_exists(self, connection: Any, schema_name: str, table_name: str) -> bool:
        result = connection.execute(
            self._sql_text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                LIMIT 1
                """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        )
        if hasattr(result, "scalar_one_or_none"):
            return result.scalar_one_or_none() is not None
        return result.scalar() is not None

    def _apply_comments(
        self,
        connection: Any,
        schema_name: str,
        table_name: str,
        filename: str,
        columns: list[dict[str, Any]],
    ) -> None:
        connection.execute(
            self._sql_text(f"COMMENT ON TABLE {qualified_table_name(schema_name, table_name)} IS :comment"),
            {"comment": f"Imported from file: {filename}"},
        )
        for column in columns:
            connection.execute(
                self._sql_text(
                    f"COMMENT ON COLUMN {qualified_table_name(schema_name, table_name)}."
                    f"{quote_identifier(column['name'])} IS :comment"
                ),
                {
                    "comment": (
                        f"Original column: {column['original_name']}; "
                        f"inferred type: {column['type']}"
                    )
                },
            )

    def _preview_service(self) -> ImportPreviewService:
        if self.preview_service is None:
            self.preview_service = ImportPreviewService()
        return self.preview_service

    def _schema_refresh_service(self) -> Any:
        if self.schema_refresh_service is None:
            from app.services.schema_refresh_service import SchemaRefreshService

            self.schema_refresh_service = SchemaRefreshService()
        return self.schema_refresh_service

    def _engine(self) -> Any:
        if self.db_engine is None:
            from app.db.database import engine

            self.db_engine = engine
        return self.db_engine

    def _sql_text(self, sql: str) -> Any:
        if self.sql_text_factory is not None:
            return self.sql_text_factory(sql)

        from sqlalchemy import text

        return text(sql)


def _build_create_table_sql(schema_name: str, table_name: str, columns: list[dict[str, Any]]) -> str:
    column_definitions = [
        f"{quote_identifier(column['name'])} {POSTGRES_TYPE_BY_IMPORT_TYPE[column['type']]}"
        for column in columns
    ]
    return f"CREATE TABLE {qualified_table_name(schema_name, table_name)} ({', '.join(column_definitions)})"


def _build_insert_sql(schema_name: str, table_name: str, columns: list[dict[str, Any]]) -> str:
    column_names = [column["name"] for column in columns]
    quoted_columns = ", ".join(quote_identifier(column_name) for column_name in column_names)
    placeholders = ", ".join(f":{column_name}" for column_name in column_names)
    return f"INSERT INTO {qualified_table_name(schema_name, table_name)} ({quoted_columns}) VALUES ({placeholders})"


def _prepare_insert_row(row: dict[str, Any], columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        column["name"]: _convert_value(row.get(column["name"]), column["type"], column["name"])
        for column in columns
    }


def _convert_value(value: Any, import_type: str, column_name: str) -> Any:
    if _is_blank_value(value):
        return None
    if import_type == "text":
        return str(value)
    if import_type == "integer":
        return _to_integer(value, column_name)
    if import_type == "numeric":
        return _to_decimal(value, column_name)
    if import_type == "boolean":
        return _to_boolean(value, column_name)
    if import_type == "date":
        return _to_date(value, column_name)
    if import_type == "timestamp":
        return _to_datetime(value, column_name)
    return str(value)


def _to_integer(value: Any, column_name: str) -> int:
    if isinstance(value, bool):
        raise ImportCommitError(f"字段 {column_name} 的值不能转换为整数。")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ImportCommitError(f"字段 {column_name} 的值不能转换为整数。") from exc


def _to_decimal(value: Any, column_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ImportCommitError(f"字段 {column_name} 的值不能转换为数字。") from exc


def _to_boolean(value: Any, column_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y"}:
            return True
        if lowered in {"false", "no", "n"}:
            return False
    raise ImportCommitError(f"字段 {column_name} 的值不能转换为布尔值。")


def _to_date(value: Any, column_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed_date = _parse_date_string(value)
        if parsed_date is not None:
            return parsed_date
        parsed_datetime = _parse_datetime_string(value)
        if parsed_datetime is not None:
            return parsed_datetime.date()
    raise ImportCommitError(f"字段 {column_name} 的值不能转换为日期。")


def _to_datetime(value: Any, column_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        parsed_datetime = _parse_datetime_string(value)
        if parsed_datetime is not None:
            return parsed_datetime
        parsed_date = _parse_date_string(value)
        if parsed_date is not None:
            return datetime.combine(parsed_date, datetime.min.time())
    raise ImportCommitError(f"字段 {column_name} 的值不能转换为时间。")


def _parse_date_string(value: str) -> date | None:
    text = value.strip()
    for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _parse_datetime_string(value: str) -> datetime | None:
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for datetime_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ):
        try:
            return datetime.strptime(text, datetime_format)
        except ValueError:
            continue
    return None


def _is_blank_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False
