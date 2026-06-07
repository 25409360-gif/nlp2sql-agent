import unittest
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.import_data import create_import_commit_service, router
from app.services.import_commit_service import DuplicateImportTableError
from app.utils.error_handling import register_error_handlers
from main import create_app


class FakeImportCommitService:
    def commit_file(self, table_name, filename, content, content_type=""):
        return {
            "filename": filename,
            "extension": "csv",
            "schema_name": "public",
            "table_name": table_name,
            "columns": [
                {
                    "name": "name",
                    "original_name": "Name",
                    "type": "text",
                    "nullable": False,
                    "sample_values": ["Alice"],
                }
            ],
            "row_count": 1,
            "column_count": 1,
            "created": True,
            "warnings": [],
            "schema_refresh": {
                "imported_table_visible": True,
                "metadata_table_count": 11,
                "document_count": 11,
                "indexed_document_count": 11,
                "vector_inserted_count": 11,
            },
        }


class DuplicateImportCommitService:
    def commit_file(self, table_name, filename, content, content_type=""):
        raise DuplicateImportTableError(f"数据表已存在：{table_name}")


class ImportAPITest(unittest.TestCase):
    def create_client(self, commit_service=None) -> TestClient:
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router, prefix="/api")
        if commit_service is not None:
            app.dependency_overrides[create_import_commit_service] = lambda: commit_service
        return TestClient(app)

    def test_capabilities_endpoint_lists_supported_file_types(self) -> None:
        client = self.create_client()

        response = client.get("/api/import/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["supported_extensions"], ["csv", "xlsx"])
        self.assertTrue(payload["upload_ready"])

    def test_upload_check_accepts_csv_file(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/upload-check",
            files={"file": ("users.csv", b"name\nAlice\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filename"], "users.csv")
        self.assertEqual(payload["extension"], "csv")
        self.assertEqual(payload["content_type"], "text/csv")
        self.assertEqual(payload["size_bytes"], len(b"name\nAlice\n"))
        self.assertTrue(payload["supported"])

    def test_upload_check_accepts_xlsx_file_extension(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/upload-check",
            files={
                "file": (
                    "users.xlsx",
                    b"placeholder",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["extension"], "xlsx")

    def test_upload_check_rejects_unsupported_file_type(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/upload-check",
            files={"file": ("users.txt", b"name\nAlice\n", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["details"]["extension"], "txt")

    def test_preview_csv_returns_columns_rows_and_inferred_types(self) -> None:
        client = self.create_client()
        csv_content = (
            "\n"
            "Name,Age,Started,Revenue,Active,,Age\n"
            "Alice,30,2024-01-01,12.5,true,,31\n"
            "Bob,41,2024-02-02,100.75,false,,42\n"
            "\n"
        ).encode("utf-8")

        response = client.post(
            "/api/import/preview?preview_limit=1",
            files={"file": ("users.csv", csv_content, "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filename"], "users.csv")
        self.assertEqual(payload["extension"], "csv")
        self.assertEqual(payload["encoding"], "utf-8-sig")
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(payload["column_count"], 6)
        self.assertEqual(payload["preview_row_count"], 1)
        self.assertEqual(
            [column["name"] for column in payload["columns"]],
            ["name", "age", "started", "revenue", "active", "age_2"],
        )
        self.assertEqual(
            [column["type"] for column in payload["columns"]],
            ["text", "integer", "date", "numeric", "boolean", "integer"],
        )
        self.assertEqual(
            payload["rows"],
            [
                {
                    "name": "Alice",
                    "age": "30",
                    "started": "2024-01-01",
                    "revenue": "12.5",
                    "active": "true",
                    "age_2": "31",
                }
            ],
        )
        self.assertTrue(any("空行" in warning for warning in payload["warnings"]))
        self.assertTrue(any("空列" in warning for warning in payload["warnings"]))
        self.assertTrue(any("Age 重复" in warning for warning in payload["warnings"]))

    def test_preview_csv_preserves_original_chinese_headers_with_safe_names(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/preview",
            files={
                "file": (
                    "departments.csv",
                    "姓名,部门\n王子轩,研发部\n李佳怡,产品部\n".encode("utf-8"),
                    "text/csv",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([column["original_name"] for column in payload["columns"]], ["姓名", "部门"])
        self.assertEqual([column["name"] for column in payload["columns"]], ["column_1", "column_2"])
        self.assertEqual(payload["rows"][0], {"column_1": "王子轩", "column_2": "研发部"})
        self.assertTrue(any("姓名 已规范化为 column_1" in warning for warning in payload["warnings"]))

    def test_preview_xlsx_reads_first_sheet(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/preview",
            files={
                "file": (
                    "scores.xlsx",
                    _xlsx_bytes(
                        first_sheet_rows=[
                            ["Employee Name", "Score", "Checked At"],
                            ["Alice", 95, "2026-06-01 10:30:00"],
                            ["Bob", 88, "2026-06-02 11:00:00"],
                        ],
                        second_sheet_rows=[["Ignored"], ["value"]],
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sheet_name"], "First")
        self.assertEqual(payload["row_count"], 2)
        self.assertEqual(
            [column["name"] for column in payload["columns"]],
            ["employee_name", "score", "checked_at"],
        )
        self.assertEqual(
            [column["type"] for column in payload["columns"]],
            ["text", "integer", "timestamp"],
        )
        self.assertEqual(payload["rows"][0]["employee_name"], "Alice")
        self.assertEqual(payload["rows"][0]["score"], 95)

    def test_preview_rejects_empty_file(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/preview",
            files={"file": ("empty.csv", b"", "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_preview_rejects_unsupported_file_type(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/import/preview",
            files={"file": ("users.txt", b"name\nAlice\n", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["details"]["extension"], "txt")

    def test_commit_endpoint_returns_import_result(self) -> None:
        client = self.create_client(FakeImportCommitService())

        response = client.post(
            "/api/import/commit",
            data={"table_name": "uploaded_users"},
            files={"file": ("users.csv", b"Name\nAlice\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table_name"], "uploaded_users")
        self.assertEqual(payload["schema_name"], "public")
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["column_count"], 1)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["columns"][0]["name"], "name")
        self.assertTrue(payload["schema_refresh"]["imported_table_visible"])

    def test_commit_endpoint_returns_conflict_for_duplicate_table(self) -> None:
        client = self.create_client(DuplicateImportCommitService())

        response = client.post(
            "/api/import/commit",
            data={"table_name": "uploaded_users"},
            files={"file": ("users.csv", b"Name\nAlice\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_request")
        self.assertEqual(payload["error"]["details"]["table_name"], "uploaded_users")

    def test_import_router_is_registered_on_main_app(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/import/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["supported_extensions"], ["csv", "xlsx"])


def _xlsx_bytes(first_sheet_rows, second_sheet_rows) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    first = workbook.active
    first.title = "First"
    for row in first_sheet_rows:
        first.append(row)

    second = workbook.create_sheet("Second")
    for row in second_sheet_rows:
        second.append(row)

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
