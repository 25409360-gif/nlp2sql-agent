import re
import unittest
from datetime import date
from decimal import Decimal

from app.services.table_data_safety import InvalidPaginationError, InvalidTableNameError, UnknownTableError
from app.services.table_data_service import ProtectedTableDeletionError, TableDataService


class FakeSchemaService:
    schema = "public"

    def __init__(self) -> None:
        self.metadata = [
            {
                "name": "users",
                "description": "用户信息表",
                "primary_keys": ["id"],
                "columns": [
                    {"name": "id"},
                    {"name": "name"},
                    {"name": "score"},
                    {"name": "created_at"},
                    {"name": "payload"},
                ],
            },
            {
                "name": "imported_orders",
                "description": "Imported from file: orders.xlsx",
                "primary_keys": [],
                "columns": [
                    {"name": "order_no"},
                    {"name": "amount"},
                ],
            },
            {
                "name": "tasks",
                "description": "任务表",
                "primary_keys": ["id"],
                "columns": [
                    {"name": "id"},
                    {"name": "title"},
                ],
            },
        ]

    def get_metadata(self, refresh=False):
        return self.metadata


class FakeSchemaRefreshService:
    def __init__(self) -> None:
        self.deleted_table_names = []

    def refresh_after_table_delete(self, table_names):
        self.deleted_table_names = list(table_names)
        return {
            "deleted_tables_absent": True,
            "deleted_tables": list(table_names),
            "metadata_table_count": 2,
            "document_count": 2,
            "indexed_document_count": 2,
            "vector_inserted_count": 2,
        }


class FakeEngine:
    def __init__(self) -> None:
        self.rows_by_table = {
            "users": [
                {
                    "id": 1,
                    "name": "王子轩",
                    "score": Decimal("9.5"),
                    "created_at": date(2026, 6, 6),
                    "payload": b"abc",
                },
                {
                    "id": 2,
                    "name": "李佳怡",
                    "score": Decimal("8.0"),
                    "created_at": date(2026, 6, 7),
                    "payload": b"def",
                },
                {
                    "id": 3,
                    "name": "张诗涵",
                    "score": Decimal("7.5"),
                    "created_at": date(2026, 6, 8),
                    "payload": b"ghi",
                },
            ],
            "tasks": [
                {"id": 1, "title": "整理数据"},
            ],
            "imported_orders": [
                {"order_no": "A001", "amount": 100},
            ],
        }
        self.connection = FakeConnection(self.rows_by_table)

    def connect(self):
        return self.connection

    def begin(self):
        return self.connection


class FakeConnection:
    def __init__(self, rows_by_table) -> None:
        self.rows_by_table = rows_by_table
        self.executed = []
        self.transaction = FakeTransaction()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return self.transaction

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))

        if sql == "SET TRANSACTION READ ONLY":
            return FakeScalarResult(None)

        table_name = self._table_name(sql)
        if sql.startswith("DROP TABLE"):
            self.rows_by_table.pop(table_name, None)
            return FakeScalarResult(None)

        rows = self.rows_by_table[table_name]

        if sql.startswith("SELECT COUNT(*)"):
            return FakeScalarResult(len(rows))

        limit = params["limit"]
        offset = params["offset"]
        return FakeRowsResult(rows[offset : offset + limit])

    def _table_name(self, sql):
        match = re.search(r'"public"\."([^"]+)"', sql)
        if not match:
            raise AssertionError(f"Unexpected SQL: {sql}")
        return match.group(1)


class FakeTransaction:
    def __init__(self) -> None:
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1


class FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one(self):
        return self.value


class FakeRowsResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class TableDataServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema_service = FakeSchemaService()
        self.engine = FakeEngine()
        self.schema_refresh_service = FakeSchemaRefreshService()
        self.service = TableDataService(
            schema_service=self.schema_service,
            db_engine=self.engine,
            schema_refresh_service=self.schema_refresh_service,
            sql_text_factory=lambda sql: sql,
        )

    def test_lists_tables_with_column_count(self) -> None:
        tables = self.service.list_tables()

        self.assertEqual(
            tables,
            [
                {"name": "users", "description": "用户信息表", "column_count": 5, "deletable": False},
                {
                    "name": "imported_orders",
                    "description": "Imported from file: orders.xlsx",
                    "column_count": 2,
                    "deletable": True,
                },
                {"name": "tasks", "description": "任务表", "column_count": 2, "deletable": False},
            ],
        )
        self.assertFalse(tables[0]["deletable"])
        self.assertTrue(tables[1]["deletable"])

    def test_fetches_paginated_rows_and_counts_total_rows(self) -> None:
        result = self.service.get_table_rows("users", limit=2, offset=1)

        self.assertEqual(result["table_name"], "users")
        self.assertEqual(result["columns"], ["id", "name", "score", "created_at", "payload"])
        self.assertEqual(result["limit"], 2)
        self.assertEqual(result["offset"], 1)
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["total_count"], 3)
        self.assertEqual(
            result["rows"],
            [
                {
                    "id": 2,
                    "name": "李佳怡",
                    "score": 8.0,
                    "created_at": "2026-06-07",
                    "payload": "646566",
                },
                {
                    "id": 3,
                    "name": "张诗涵",
                    "score": 7.5,
                    "created_at": "2026-06-08",
                    "payload": "676869",
                },
            ],
        )

    def test_fetches_tasks_rows_and_columns(self) -> None:
        result = self.service.get_table_rows("tasks", limit=50, offset=0)

        self.assertEqual(result["table_name"], "tasks")
        self.assertEqual(result["columns"], ["id", "title"])
        self.assertEqual(result["rows"], [{"id": 1, "title": "整理数据"}])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["total_count"], 1)

    def test_pagination_changes_returned_rows(self) -> None:
        first_page = self.service.get_table_rows("users", limit=1, offset=0)
        second_page = self.service.get_table_rows("users", limit=1, offset=1)

        self.assertEqual(first_page["rows"], [
            {"id": 1, "name": "王子轩", "score": 9.5, "created_at": "2026-06-06", "payload": "616263"}
        ])
        self.assertEqual(second_page["rows"], [
            {"id": 2, "name": "李佳怡", "score": 8.0, "created_at": "2026-06-07", "payload": "646566"}
        ])

    def test_uses_read_only_transaction_and_constrained_sql(self) -> None:
        self.service.get_table_rows("tasks", limit=1, offset=0)

        executed = self.engine.connection.executed
        self.assertEqual(executed[0], ("SET TRANSACTION READ ONLY", None))
        self.assertEqual(executed[1], ('SELECT COUNT(*) AS total_count FROM "public"."tasks"', None))
        self.assertEqual(
            executed[2],
            ('SELECT * FROM "public"."tasks" ORDER BY "id" LIMIT :limit OFFSET :offset', {"limit": 1, "offset": 0}),
        )
        self.assertEqual(self.engine.connection.transaction.rollback_count, 1)

    def test_caps_limit(self) -> None:
        result = self.service.get_table_rows("users", limit=500, offset=0)

        self.assertEqual(result["limit"], 100)

    def test_rejects_unknown_and_invalid_table_names(self) -> None:
        with self.assertRaises(UnknownTableError):
            self.service.get_table_rows("orders")

        with self.assertRaises(InvalidTableNameError):
            self.service.get_table_rows("users;drop")

    def test_rejects_negative_offset(self) -> None:
        with self.assertRaises(InvalidPaginationError):
            self.service.get_table_rows("users", offset=-1)

    def test_deletes_imported_tables_and_refreshes_schema(self) -> None:
        result = self.service.delete_tables(["imported_orders"])

        self.assertEqual(result["deleted_tables"], ["imported_orders"])
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(self.schema_refresh_service.deleted_table_names, ["imported_orders"])
        self.assertNotIn("imported_orders", self.engine.rows_by_table)
        self.assertIn(('DROP TABLE "public"."imported_orders"', None), self.engine.connection.executed)

    def test_rejects_deleting_protected_system_table(self) -> None:
        with self.assertRaises(ProtectedTableDeletionError):
            self.service.delete_tables(["users"])

        self.assertIn("users", self.engine.rows_by_table)


if __name__ == "__main__":
    unittest.main()
