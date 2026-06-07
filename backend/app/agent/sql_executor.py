import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as time_type
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.logging import get_logger, sanitize_for_log
from app.db.database import engine

logger = get_logger(__name__)


@dataclass
class SQLExecutionResult:
    success: bool
    sql: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    truncated: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLExecutor:
    def __init__(
        self,
        db_engine: Engine | None = None,
        statement_timeout_ms: int | None = None,
        max_rows: int | None = None,
    ) -> None:
        self.engine = db_engine or engine
        self.statement_timeout_ms = (
            statement_timeout_ms if statement_timeout_ms is not None else settings.sql_statement_timeout_ms
        )
        self.max_rows = max_rows if max_rows is not None else settings.sql_executor_max_rows

        if self.statement_timeout_ms <= 0:
            raise ValueError("statement timeout must be greater than 0")
        if self.max_rows <= 0:
            raise ValueError("executor max rows must be greater than 0")

    def execute(self, validation_result: dict[str, Any]) -> dict[str, Any]:
        if not validation_result.get("valid"):
            logger.warning(
                "sql.execute.rejected reason=%s",
                sanitize_for_log(validation_result.get("error") or "SQL must be validated before execution"),
            )
            return SQLExecutionResult(
                success=False,
                sql=validation_result.get("safe_sql"),
                error=validation_result.get("error") or "SQL must be validated before execution",
            ).to_dict()

        sql = validation_result.get("safe_sql")
        if not sql:
            logger.warning("sql.execute.rejected reason=missing_safe_sql")
            return SQLExecutionResult(
                success=False,
                sql=None,
                error="Validated SQL result does not contain safe_sql",
            ).to_dict()

        started_at = time.perf_counter()
        logger.info("sql.execute.start sql=%s", sanitize_for_log(sql))
        try:
            with self.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    connection.execute(text(f"SET LOCAL statement_timeout = {int(self.statement_timeout_ms)}"))
                    result = connection.execute(text(sql))
                    rows = result.fetchmany(self.max_rows + 1)
                    columns = list(result.keys())
                    transaction.rollback()
                except Exception:
                    transaction.rollback()
                    raise
        except SQLAlchemyError as exc:
            duration_ms = self._elapsed_ms(started_at)
            logger.warning(
                "sql.execute.error duration_ms=%s error=%s sql=%s",
                duration_ms,
                sanitize_for_log(str(exc)),
                sanitize_for_log(sql),
            )
            return SQLExecutionResult(
                success=False,
                sql=sql,
                execution_time_ms=duration_ms,
                error=str(exc),
            ).to_dict()

        truncated = len(rows) > self.max_rows
        visible_rows = rows[: self.max_rows]
        duration_ms = self._elapsed_ms(started_at)
        logger.info(
            "sql.execute.end row_count=%s truncated=%s duration_ms=%s",
            len(visible_rows),
            truncated,
            duration_ms,
        )
        return SQLExecutionResult(
            success=True,
            sql=sql,
            columns=columns,
            rows=[self._row_to_dict(row, columns) for row in visible_rows],
            row_count=len(visible_rows),
            execution_time_ms=duration_ms,
            truncated=truncated,
            error=None,
        ).to_dict()

    def _row_to_dict(self, row: Any, columns: list[str]) -> dict[str, Any]:
        mapping = row._mapping
        return {column: self._to_json_value(mapping[column]) for column in columns}

    def _to_json_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date, time_type)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.hex()
        return str(value)

    def _elapsed_ms(self, started_at: float) -> float:
        return round((time.perf_counter() - started_at) * 1000, 3)
