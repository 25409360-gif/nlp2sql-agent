from copy import deepcopy
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine.reflection import Inspector

from app.core.config import settings
from app.db.database import engine
from app.services.schema_descriptions import COLUMN_DESCRIPTIONS, TABLE_DESCRIPTIONS


class SchemaService:
    _table_list_cache: list[dict[str, Any]] | None = None
    _table_schema_cache: dict[str, dict[str, Any]] = {}
    _metadata_cache: list[dict[str, Any]] | None = None

    def __init__(self) -> None:
        self.schema = settings.db_schema
        self.inspector: Inspector = inspect(engine)

    @classmethod
    def clear_cache(cls) -> None:
        cls._table_list_cache = None
        cls._table_schema_cache = {}
        cls._metadata_cache = None

    def list_tables(self, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh and self._table_list_cache is not None:
            return deepcopy(self._table_list_cache)

        table_names = self.inspector.get_table_names(schema=self.schema)
        tables = [
            {
                "name": table_name,
                "description": self._get_table_description(table_name),
            }
            for table_name in sorted(table_names)
        ]
        self.__class__._table_list_cache = tables
        return deepcopy(tables)

    def get_metadata(self, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh and self._metadata_cache is not None:
            return deepcopy(self._metadata_cache)

        metadata = []
        for table in self.list_tables(refresh=refresh):
            if not table.get("name"):
                continue
            table_schema = self.get_table_schema(table["name"], refresh=refresh)
            if table_schema is not None:
                metadata.append(table_schema)

        self.__class__._metadata_cache = metadata
        return deepcopy(metadata)

    def get_table_schema(self, table_name: str, refresh: bool = False) -> dict[str, Any] | None:
        if not refresh and table_name in self._table_schema_cache:
            return deepcopy(self._table_schema_cache[table_name])

        table_names = {table["name"] for table in self.list_tables(refresh=refresh)}
        if table_name not in table_names:
            return None

        primary_keys = self._get_primary_keys(table_name)
        foreign_keys = self._get_foreign_keys(table_name)
        indexes = self._get_indexes(table_name)

        columns = []
        for column in self.inspector.get_columns(table_name, schema=self.schema):
            column_name = column["name"]
            columns.append(
                {
                    "name": column_name,
                    "type": str(column["type"]),
                    "nullable": bool(column.get("nullable", True)),
                    "primary_key": column_name in primary_keys,
                    "description": self._get_column_description(table_name, column),
                }
            )

        table_schema = {
            "name": table_name,
            "schema": self.schema,
            "description": self._get_table_description(table_name),
            "columns": columns,
            "primary_keys": sorted(primary_keys),
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }
        self.__class__._table_schema_cache[table_name] = table_schema
        return deepcopy(table_schema)

    def _get_primary_keys(self, table_name: str) -> set[str]:
        constraint = self.inspector.get_pk_constraint(table_name, schema=self.schema)
        return set(constraint.get("constrained_columns") or [])

    def _get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        foreign_keys = []
        for foreign_key in self.inspector.get_foreign_keys(table_name, schema=self.schema):
            foreign_keys.append(
                {
                    "columns": foreign_key.get("constrained_columns") or [],
                    "referred_schema": foreign_key.get("referred_schema") or self.schema,
                    "referred_table": foreign_key.get("referred_table"),
                    "referred_columns": foreign_key.get("referred_columns") or [],
                }
            )
        return foreign_keys

    def _get_indexes(self, table_name: str) -> list[dict[str, Any]]:
        indexes = []
        for index in self.inspector.get_indexes(table_name, schema=self.schema):
            indexes.append(
                {
                    "name": index.get("name"),
                    "columns": index.get("column_names") or [],
                    "unique": bool(index.get("unique", False)),
                }
            )
        return indexes

    def _get_table_description(self, table_name: str) -> str:
        static_description = TABLE_DESCRIPTIONS.get(table_name, "")
        if static_description:
            return static_description
        return self._get_table_comment(table_name)

    def _get_column_description(self, table_name: str, column: dict[str, Any]) -> str:
        column_name = column["name"]
        static_description = COLUMN_DESCRIPTIONS.get(table_name, {}).get(column_name, "")
        if static_description:
            return static_description
        return str(column.get("comment") or "")

    def _get_table_comment(self, table_name: str) -> str:
        get_table_comment = getattr(self.inspector, "get_table_comment", None)
        if not callable(get_table_comment):
            return ""

        try:
            comment = get_table_comment(table_name, schema=self.schema)
        except Exception:
            return ""

        if isinstance(comment, dict):
            return str(comment.get("text") or "")
        return str(comment or "")
