import unittest
from io import BytesIO

from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.services.import_commit_service import (
    DuplicateImportTableError,
    EmptyImportDataError,
    ImportCommitService,
)
from app.services.schema_document_service import SchemaDocumentService
from app.services.schema_retriever import SchemaRetriever
from app.services.schema_service import SchemaService
from app.services.table_data_service import TableDataService
from app.services.table_data_safety import InvalidTableNameError, qualified_table_name


TEST_TABLES = [
    "import_test_people",
    "import_test_scores",
    "import_test_many_rows",
    "import_test_duplicate",
    "import_test_empty",
    "import_test_rollback",
    "import_test_refresh",
    "import_test_dates",
]


class FakeSchemaRefreshService:
    def refresh_after_import(self, table_name):
        return {
            "imported_table_visible": True,
            "metadata_table_count": 1,
            "document_count": 1,
            "indexed_document_count": 1,
            "vector_inserted_count": 1,
        }


class ImportCommitServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ImportCommitService(schema_refresh_service=FakeSchemaRefreshService())
        self.reindex_after_drop = False
        self.drop_test_tables()

    def tearDown(self) -> None:
        self.drop_test_tables()
        if self.reindex_after_drop:
            SchemaRetriever().index_schema(refresh=True, reset=True)

    def drop_test_tables(self) -> None:
        with engine.begin() as connection:
            for table_name in TEST_TABLES:
                connection.execute(text(f"DROP TABLE IF EXISTS {qualified_table_name(settings.db_schema, table_name)}"))
        SchemaService.clear_cache()

    def test_commit_csv_creates_table_and_inserts_rows(self) -> None:
        result = self.service.commit_file(
            table_name="import_test_people",
            filename="people.csv",
            content=(
                "Name,Age,Started,Revenue,Active\n"
                "Alice,30,2024-01-01,12.5,true\n"
                "Bob,41,2024-01-02,100.75,false\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["table_name"], "import_test_people")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["column_count"], 5)

        rows = self.fetch_rows(
            f"""
            SELECT "name", "age", "started", "revenue", "active"
            FROM {qualified_table_name(settings.db_schema, "import_test_people")}
            ORDER BY "name"
            """
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Alice")
        self.assertEqual(rows[0]["age"], 30)
        self.assertEqual(str(rows[0]["started"]), "2024-01-01")
        self.assertEqual(str(rows[0]["revenue"]), "12.5")
        self.assertTrue(rows[0]["active"])

    def test_commit_xlsx_creates_table_and_inserts_rows(self) -> None:
        result = self.service.commit_file(
            table_name="import_test_scores",
            filename="scores.xlsx",
            content=create_xlsx_bytes(
                [
                    ["Employee Name", "Score", "Checked At"],
                    ["Alice", 95, "2026-06-01 10:30:00"],
                    ["Bob", 88, "2026-06-02 11:00:00"],
                ]
            ),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual([column["name"] for column in result["columns"]], ["employee_name", "score", "checked_at"])

        rows = self.fetch_rows(
            f"""
            SELECT "employee_name", "score", "checked_at"
            FROM {qualified_table_name(settings.db_schema, "import_test_scores")}
            ORDER BY "employee_name"
            """
        )
        self.assertEqual(rows[0]["employee_name"], "Alice")
        self.assertEqual(rows[0]["score"], 95)
        self.assertEqual(str(rows[0]["checked_at"]), "2026-06-01 10:30:00")

    def test_commit_csv_imports_all_rows_not_only_preview_rows(self) -> None:
        content = "Name,Score\n" + "\n".join(f"User {index},{index}" for index in range(1, 61))

        result = self.service.commit_file(
            table_name="import_test_many_rows",
            filename="many_rows.csv",
            content=content.encode("utf-8"),
            content_type="text/csv",
        )

        self.assertEqual(result["row_count"], 60)
        rows = self.fetch_rows(
            f"""
            SELECT COUNT(*) AS row_count, MAX("score") AS max_score
            FROM {qualified_table_name(settings.db_schema, "import_test_many_rows")}
            """
        )
        self.assertEqual(rows[0]["row_count"], 60)
        self.assertEqual(rows[0]["max_score"], 60)

    def test_commit_accepts_preview_supported_date_formats(self) -> None:
        result = self.service.commit_file(
            table_name="import_test_dates",
            filename="dates.csv",
            content=(
                "Observation Date,Measured At\n"
                "2026/06/01,2026/06/01 08:30\n"
                "2026.06.02,2026-06-02T09:45:00\n"
                "06/03/2026,2026-06-03 10:15:00\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        self.assertTrue(result["created"])
        self.assertEqual([column["type"] for column in result["columns"]], ["date", "timestamp"])

        rows = self.fetch_rows(
            f"""
            SELECT "observation_date", "measured_at"
            FROM {qualified_table_name(settings.db_schema, "import_test_dates")}
            ORDER BY "observation_date"
            """
        )
        self.assertEqual([str(row["observation_date"]) for row in rows], ["2026-06-01", "2026-06-02", "2026-06-03"])
        self.assertEqual(str(rows[0]["measured_at"]), "2026-06-01 08:30:00")

    def test_duplicate_table_is_rejected(self) -> None:
        content = "Name\nAlice\n".encode("utf-8")
        self.service.commit_file(
            table_name="import_test_duplicate",
            filename="people.csv",
            content=content,
            content_type="text/csv",
        )

        with self.assertRaises(DuplicateImportTableError):
            self.service.commit_file(
                table_name="import_test_duplicate",
                filename="people.csv",
                content=content,
                content_type="text/csv",
            )

    def test_invalid_table_name_is_rejected(self) -> None:
        with self.assertRaises(InvalidTableNameError):
            self.service.commit_file(
                table_name="bad-name",
                filename="people.csv",
                content="Name\nAlice\n".encode("utf-8"),
                content_type="text/csv",
            )

    def test_empty_data_is_rejected_without_creating_table(self) -> None:
        with self.assertRaises(EmptyImportDataError):
            self.service.commit_file(
                table_name="import_test_empty",
                filename="empty.csv",
                content="Name,Age\n".encode("utf-8"),
                content_type="text/csv",
            )

        self.assertFalse(self.table_exists("import_test_empty"))

    def test_insert_failure_rolls_back_created_table(self) -> None:
        with self.assertRaises(Exception):
            self.service.commit_file(
                table_name="import_test_rollback",
                filename="bad.csv",
                content=("Age\n999999999999999999999999999999\n").encode("utf-8"),
                content_type="text/csv",
            )

        self.assertFalse(self.table_exists("import_test_rollback"))

    def test_commit_refreshes_schema_documents_and_retrieval_index(self) -> None:
        self.reindex_after_drop = True
        service = ImportCommitService()

        result = service.commit_file(
            table_name="import_test_refresh",
            filename="refresh.csv",
            content=("Name,Age\nAlice,30\n").encode("utf-8"),
            content_type="text/csv",
        )

        self.assertTrue(result["schema_refresh"]["imported_table_visible"])
        self.assertGreaterEqual(result["schema_refresh"]["document_count"], 1)
        self.assertGreaterEqual(result["schema_refresh"]["vector_inserted_count"], 1)

        table_names = {table["name"] for table in TableDataService().list_tables(refresh=True)}
        self.assertIn("import_test_refresh", table_names)

        rows_result = TableDataService().get_table_rows("import_test_refresh")
        self.assertEqual(rows_result["rows"], [{"name": "Alice", "age": 30}])

        documents = SchemaDocumentService().build_documents(refresh=True)
        imported_document = next(
            document for document in documents if document["table_name"] == "import_test_refresh"
        )
        self.assertIn("Original column: Name", imported_document["content"])

        retrieve_result = SchemaRetriever().retrieve("import_test_refresh", top_k=5)
        self.assertIn("import_test_refresh", [match["table_name"] for match in retrieve_result["matches"]])

    def fetch_rows(self, sql: str):
        with engine.connect() as connection:
            return list(connection.execute(text(sql)).mappings().all())

    def table_exists(self, table_name: str) -> bool:
        with engine.connect() as connection:
            return bool(
                connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = :schema_name
                          AND table_name = :table_name
                        """
                    ),
                    {"schema_name": settings.db_schema, "table_name": table_name},
                ).scalar()
            )


def create_xlsx_bytes(rows) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Scores"
    for row in rows:
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


if __name__ == "__main__":
    unittest.main()
