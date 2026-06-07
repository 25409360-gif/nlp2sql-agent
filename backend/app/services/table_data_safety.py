import re
from dataclasses import dataclass
from datetime import date, datetime, time as time_type
from decimal import Decimal
from math import isfinite
from typing import Any, Iterable, Mapping


DEFAULT_TABLE_ROWS_LIMIT = 50
MAX_TABLE_ROWS_LIMIT = 100
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TableDataSafetyError(ValueError):
    pass


class InvalidTableNameError(TableDataSafetyError):
    pass


class UnknownTableError(TableDataSafetyError):
    pass


class InvalidPaginationError(TableDataSafetyError):
    pass


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def normalize_identifier(identifier: str, field_name: str = "identifier") -> str:
    normalized = str(identifier or "").strip()
    if not normalized:
        raise InvalidTableNameError(f"{field_name} is required")
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise InvalidTableNameError(f"{field_name} contains unsafe characters")
    return normalized


def validate_table_name(table_name: str, available_tables: Iterable[str]) -> str:
    normalized = normalize_identifier(table_name, field_name="table_name")
    if normalized not in {str(table) for table in available_tables}:
        raise UnknownTableError(f"Unknown table: {normalized}")
    return normalized


def normalize_pagination(
    limit: int | None = None,
    offset: int | None = None,
    default_limit: int = DEFAULT_TABLE_ROWS_LIMIT,
    max_limit: int = MAX_TABLE_ROWS_LIMIT,
) -> Pagination:
    if default_limit <= 0:
        raise InvalidPaginationError("default limit must be greater than 0")
    if max_limit <= 0:
        raise InvalidPaginationError("max limit must be greater than 0")
    if default_limit > max_limit:
        raise InvalidPaginationError("default limit must be less than or equal to max limit")

    try:
        requested_limit = default_limit if limit is None else int(limit)
        requested_offset = 0 if offset is None else int(offset)
    except (TypeError, ValueError) as exc:
        raise InvalidPaginationError("limit and offset must be integers") from exc

    if requested_limit <= 0:
        raise InvalidPaginationError("limit must be greater than 0")
    if requested_offset < 0:
        raise InvalidPaginationError("offset must not be negative")

    return Pagination(limit=min(requested_limit, max_limit), offset=requested_offset)


def quote_identifier(identifier: str) -> str:
    normalized = normalize_identifier(identifier)
    return f'"{normalized}"'


def qualified_table_name(schema_name: str, table_name: str) -> str:
    return f"{quote_identifier(schema_name)}.{quote_identifier(table_name)}"


def build_table_rows_sql(schema_name: str, table_name: str, order_by: list[str] | None = None) -> str:
    sql = f"SELECT * FROM {qualified_table_name(schema_name, table_name)}"
    if order_by:
        ordered_columns = ", ".join(quote_identifier(column) for column in order_by)
        sql = f"{sql} ORDER BY {ordered_columns}"
    return f"{sql} LIMIT :limit OFFSET :offset"


def build_table_count_sql(schema_name: str, table_name: str) -> str:
    return f"SELECT COUNT(*) AS total_count FROM {qualified_table_name(schema_name, table_name)}"


def build_drop_table_sql(schema_name: str, table_name: str) -> str:
    return f"DROP TABLE {qualified_table_name(schema_name, table_name)}"


def to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else str(value)
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else str(value)
    if isinstance(value, (datetime, date, time_type)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]
    return str(value)


def row_to_json_dict(row_mapping: Mapping[str, Any], columns: list[str]) -> dict[str, Any]:
    return {column: to_json_safe(row_mapping[column]) for column in columns}
