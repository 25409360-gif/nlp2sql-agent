import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.data import create_table_data_service, router
from app.services.table_data_safety import InvalidTableNameError, UnknownTableError
from app.services.table_data_service import ProtectedTableDeletionError
from app.utils.error_handling import register_error_handlers


class FakeTableDataService:
    rows_by_table = {
        "users": [
            {"id": 1, "name": "王子轩"},
            {"id": 2, "name": "李佳怡"},
            {"id": 3, "name": "张诗涵"},
        ],
        "tasks": [
            {"id": 1, "title": "整理数据"},
            {"id": 2, "title": "检查接口"},
        ],
    }

    def __init__(self) -> None:
        self.deleted_table_names = []

    def list_tables(self):
        return [
            {"name": "users", "description": "用户信息表", "column_count": 6, "deletable": False},
            {"name": "uploaded_orders", "description": "Imported from file: orders.xlsx", "column_count": 3, "deletable": True},
            {"name": "tasks", "description": "任务表", "column_count": 8, "deletable": False},
        ]

    def get_table_rows(self, table_name, limit=50, offset=0):
        if table_name == "unknown":
            raise UnknownTableError("Unknown table: unknown")
        if table_name == "bad-name":
            raise InvalidTableNameError("table_name contains unsafe characters")

        applied_limit = min(limit, 100)
        rows = self.rows_by_table[table_name]
        return {
            "table_name": table_name,
            "columns": list(rows[0]),
            "rows": rows[offset : offset + applied_limit],
            "limit": applied_limit,
            "offset": offset,
            "row_count": len(rows[offset : offset + applied_limit]),
            "total_count": len(rows),
        }

    def delete_tables(self, table_names):
        if "unknown" in table_names:
            raise UnknownTableError("Unknown table: unknown")
        if "bad-name" in table_names:
            raise InvalidTableNameError("table_name contains unsafe characters")
        if "users" in table_names:
            raise ProtectedTableDeletionError("数据表不允许删除：users")

        self.deleted_table_names = list(table_names)
        return {
            "deleted_tables": list(table_names),
            "deleted_count": len(table_names),
            "schema_refresh": {
                "deleted_tables_absent": True,
                "deleted_tables": list(table_names),
                "metadata_table_count": 2,
                "document_count": 2,
                "indexed_document_count": 2,
                "vector_inserted_count": 2,
            },
        }


class DataAPITest(unittest.TestCase):
    def create_client(self, service):
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[create_table_data_service] = lambda: service
        return TestClient(app)

    def test_lists_data_tables(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["tables"]), 3)
        self.assertEqual(payload["tables"][0], {"name": "users", "description": "用户信息表", "column_count": 6, "deletable": False})
        self.assertTrue(payload["tables"][1]["deletable"])

    def test_reads_users_table_rows(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/users/rows?limit=50&offset=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table_name"], "users")
        self.assertEqual(payload["columns"], ["id", "name"])
        self.assertEqual(payload["rows"], [{"id": 2, "name": "李佳怡"}, {"id": 3, "name": "张诗涵"}])
        self.assertEqual(payload["limit"], 50)
        self.assertEqual(payload["offset"], 1)
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(payload["total_count"], 3)

    def test_reads_tasks_table_rows(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/tasks/rows")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table_name"], "tasks")
        self.assertEqual(payload["columns"], ["id", "title"])
        self.assertEqual(payload["rows"], [{"id": 1, "title": "整理数据"}, {"id": 2, "title": "检查接口"}])
        self.assertEqual(payload["total_count"], 2)

    def test_limit_is_capped(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/users/rows?limit=500")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limit"], 100)

    def test_pagination_changes_returned_rows(self) -> None:
        client = self.create_client(FakeTableDataService())

        first_page = client.get("/api/data/tables/users/rows?limit=1&offset=0").json()
        second_page = client.get("/api/data/tables/users/rows?limit=1&offset=1").json()

        self.assertEqual(first_page["rows"], [{"id": 1, "name": "王子轩"}])
        self.assertEqual(second_page["rows"], [{"id": 2, "name": "李佳怡"}])

    def test_unknown_table_returns_not_found(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/unknown/rows")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(payload["error"]["details"]["table_name"], "unknown")

    def test_invalid_table_name_returns_invalid_request(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/bad-name/rows")

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["details"]["table_name"], "bad-name")

    def test_negative_offset_validation(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.get("/api/data/tables/users/rows?offset=-1")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_deletes_uploaded_tables(self) -> None:
        service = FakeTableDataService()
        client = self.create_client(service)

        response = client.request("DELETE", "/api/data/tables", json={"table_names": ["uploaded_orders"]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deleted_tables"], ["uploaded_orders"])
        self.assertEqual(payload["deleted_count"], 1)
        self.assertEqual(service.deleted_table_names, ["uploaded_orders"])

    def test_rejects_deleting_system_tables(self) -> None:
        client = self.create_client(FakeTableDataService())

        response = client.request("DELETE", "/api/data/tables", json={"table_names": ["users"]})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "protected_table")


if __name__ == "__main__":
    unittest.main()
