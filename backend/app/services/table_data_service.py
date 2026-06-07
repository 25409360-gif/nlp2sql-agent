from typing import Any, Callable

from app.services.table_data_safety import (
    Pagination,
    build_table_count_sql,
    build_drop_table_sql,
    build_table_rows_sql,
    normalize_pagination,
    row_to_json_dict,
    validate_table_name,
)


IMPORTED_TABLE_DESCRIPTION_PREFIX = "Imported from file:"


class TableDeletionError(ValueError):
    pass


class ProtectedTableDeletionError(TableDeletionError):
    pass


class TableDataService:
    def __init__(
        self,
        schema_service: Any | None = None,
        db_engine: Any | None = None,
        schema_refresh_service: Any | None = None,
        schema_name: str | None = None,
        sql_text_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.schema_service = schema_service
        self.db_engine = db_engine
        self.schema_refresh_service = schema_refresh_service
        self.schema_name = schema_name
        self.sql_text_factory = sql_text_factory

    def list_tables(self, refresh: bool = False) -> list[dict[str, Any]]:
        return [
            {
                "name": table["name"],
                "description": table.get("description", ""),
                "column_count": len(table.get("columns") or []),
                "deletable": self._is_deletable_table(table),
            }
            for table in self._metadata(refresh=refresh)
            if table.get("name")
        ]

    def get_table_rows(
        self,
        table_name: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        metadata_by_name = {table["name"]: table for table in self._metadata() if table.get("name")}
        safe_table_name = validate_table_name(table_name, metadata_by_name)
        pagination = normalize_pagination(limit=limit, offset=offset)
        table_schema = metadata_by_name[safe_table_name]
        columns = [column["name"] for column in table_schema.get("columns", []) if column.get("name")]

        schema_name = self._schema_name()
        total_count, rows = self._fetch_rows(
            count_sql=build_table_count_sql(schema_name, safe_table_name),
            rows_sql=build_table_rows_sql(
                schema_name,
                safe_table_name,
                order_by=self._default_order_columns(table_schema, columns),
            ),
            pagination=pagination,
            columns=columns,
        )

        return {
            "table_name": safe_table_name,
            "columns": columns,
            "rows": rows,
            "limit": pagination.limit,
            "offset": pagination.offset,
            "row_count": len(rows),
            "total_count": total_count,
        }

    def delete_tables(self, table_names: list[str]) -> dict[str, Any]:
        if not table_names:
            raise TableDeletionError("table_names must not be empty")

        metadata_by_name = {table["name"]: table for table in self._metadata(refresh=True) if table.get("name")}
        safe_table_names = self._validated_delete_table_names(table_names, metadata_by_name)
        schema_name = self._schema_name()

        with self._engine().begin() as connection:
            for table_name in safe_table_names:
                connection.execute(self._sql_text(build_drop_table_sql(schema_name, table_name)))

        schema_refresh = self._schema_refresh_service().refresh_after_table_delete(safe_table_names)
        return {
            "deleted_tables": safe_table_names,
            "deleted_count": len(safe_table_names),
            "schema_refresh": schema_refresh,
        }

    def _fetch_rows(
        self,
        count_sql: str,
        rows_sql: str,
        pagination: Pagination,
        columns: list[str],
    ) -> tuple[int, list[dict[str, Any]]]:
        with self._engine().connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(self._sql_text("SET TRANSACTION READ ONLY"))
                count_result = connection.execute(self._sql_text(count_sql))
                total_count = int(self._scalar_one(count_result))
                rows_result = connection.execute(
                    self._sql_text(rows_sql),
                    {"limit": pagination.limit, "offset": pagination.offset},
                )
                rows = self._result_rows(rows_result, columns)
                transaction.rollback()
            except Exception:
                transaction.rollback()
                raise

        return total_count, rows

    def _result_rows(self, result: Any, columns: list[str]) -> list[dict[str, Any]]:
        if hasattr(result, "mappings"):
            return [row_to_json_dict(mapping, columns) for mapping in result.mappings().all()]

        return [
            row_to_json_dict(getattr(row, "_mapping", row), columns)
            for row in result.fetchall()
        ]

    def _scalar_one(self, result: Any) -> Any:
        if hasattr(result, "scalar_one"):
            return result.scalar_one()
        return result.scalar()

    def _metadata(self, refresh: bool = False) -> list[dict[str, Any]]:
        return self._schema_service().get_metadata(refresh=refresh)

    def _validated_delete_table_names(
        self,
        table_names: list[str],
        metadata_by_name: dict[str, dict[str, Any]],
    ) -> list[str]:
        safe_table_names = []
        for table_name in table_names:
            safe_table_name = validate_table_name(table_name, metadata_by_name)
            if safe_table_name in safe_table_names:
                continue
            table_schema = metadata_by_name[safe_table_name]
            if not self._is_deletable_table(table_schema):
                raise ProtectedTableDeletionError(f"数据表不允许删除：{safe_table_name}")
            safe_table_names.append(safe_table_name)

        if not safe_table_names:
            raise TableDeletionError("table_names must not be empty")
        return safe_table_names

    def _is_deletable_table(self, table_schema: dict[str, Any]) -> bool:
        description = str(table_schema.get("description") or "")
        return description.startswith(IMPORTED_TABLE_DESCRIPTION_PREFIX)

    def _default_order_columns(self, table_schema: dict[str, Any], columns: list[str]) -> list[str]:
        column_set = set(columns)
        primary_keys = [
            column
            for column in table_schema.get("primary_keys", [])
            if column in column_set
        ]
        if primary_keys:
            return primary_keys
        return columns[:1]

    def _schema_name(self) -> str:
        if self.schema_name:
            return self.schema_name
        return str(getattr(self._schema_service(), "schema", "public"))

    def _schema_service(self) -> Any:
        if self.schema_service is None:
            from app.services.schema_service import SchemaService

            self.schema_service = SchemaService()
        return self.schema_service

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
