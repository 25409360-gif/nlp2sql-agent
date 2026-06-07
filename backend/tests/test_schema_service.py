from app.services.schema_descriptions import COLUMN_DESCRIPTIONS
from app.services.schema_service import SchemaService


class FakeInspector:
    def get_table_names(self, schema=None):
        assert schema == "public"
        return ["users", "attendance_records"]

    def get_pk_constraint(self, table_name, schema=None):
        assert schema == "public"
        return {"constrained_columns": ["id"]}

    def get_foreign_keys(self, table_name, schema=None):
        assert schema == "public"
        if table_name == "attendance_records":
            return [
                {
                    "constrained_columns": ["user_id"],
                    "referred_schema": None,
                    "referred_table": "users",
                    "referred_columns": ["id"],
                }
            ]
        return []

    def get_indexes(self, table_name, schema=None):
        assert schema == "public"
        if table_name == "users":
            return [{"name": "ix_users_email", "column_names": ["email"], "unique": True}]
        return []

    def get_columns(self, table_name, schema=None):
        assert schema == "public"
        columns = {
            "users": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "name", "type": "VARCHAR(100)", "nullable": False},
                {"name": "email", "type": "VARCHAR(160)", "nullable": False},
            ],
            "attendance_records": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "user_id", "type": "INTEGER", "nullable": False},
                {"name": "status", "type": "VARCHAR(40)", "nullable": False},
            ],
        }
        return columns[table_name]


class CommentInspector(FakeInspector):
    def get_table_names(self, schema=None):
        assert schema == "public"
        return ["imported_people"]

    def get_table_comment(self, table_name, schema=None):
        assert schema == "public"
        assert table_name == "imported_people"
        return {"text": "Imported from file: people.csv"}

    def get_columns(self, table_name, schema=None):
        assert schema == "public"
        assert table_name == "imported_people"
        return [
            {"name": "column_1", "type": "TEXT", "nullable": True, "comment": "Original column: 姓名"},
            {"name": "age", "type": "BIGINT", "nullable": True, "comment": "Original column: Age"},
        ]

    def get_pk_constraint(self, table_name, schema=None):
        assert schema == "public"
        return {"constrained_columns": []}


def make_schema_service() -> SchemaService:
    SchemaService.clear_cache()
    service = SchemaService.__new__(SchemaService)
    service.schema = "public"
    service.inspector = FakeInspector()
    return service


def make_comment_schema_service() -> SchemaService:
    SchemaService.clear_cache()
    service = SchemaService.__new__(SchemaService)
    service.schema = "public"
    service.inspector = CommentInspector()
    return service


def test_schema_service_lists_tables_with_descriptions() -> None:
    service = make_schema_service()

    tables = service.list_tables(refresh=True)

    assert [table["name"] for table in tables] == ["attendance_records", "users"]
    assert tables[0]["description"]
    assert tables[1]["description"]


def test_schema_service_extracts_table_columns_keys_and_relationships() -> None:
    service = make_schema_service()

    table_schema = service.get_table_schema("attendance_records", refresh=True)

    assert table_schema is not None
    assert table_schema["name"] == "attendance_records"
    assert table_schema["schema"] == "public"
    assert table_schema["primary_keys"] == ["id"]
    assert table_schema["foreign_keys"] == [
        {
            "columns": ["user_id"],
            "referred_schema": "public",
            "referred_table": "users",
            "referred_columns": ["id"],
        }
    ]
    assert [column["name"] for column in table_schema["columns"]] == ["id", "user_id", "status"]
    assert table_schema["columns"][0]["primary_key"] is True
    assert table_schema["columns"][1]["description"]


def test_schema_service_extracts_full_metadata() -> None:
    service = make_schema_service()

    metadata = service.get_metadata(refresh=True)

    assert [table["name"] for table in metadata] == ["attendance_records", "users"]
    users_schema = next(table for table in metadata if table["name"] == "users")
    assert users_schema["indexes"] == [{"name": "ix_users_email", "columns": ["email"], "unique": True}]


def test_schema_service_returns_none_for_unknown_table() -> None:
    service = make_schema_service()

    assert service.get_table_schema("missing_table", refresh=True) is None


def test_schema_service_uses_database_comments_for_imported_tables() -> None:
    service = make_comment_schema_service()

    table_schema = service.get_table_schema("imported_people", refresh=True)

    assert table_schema is not None
    assert table_schema["description"] == "Imported from file: people.csv"
    assert table_schema["columns"][0]["description"] == "Original column: 姓名"
    assert table_schema["columns"][1]["description"] == "Original column: Age"


def test_task_status_description_defines_done_as_completed() -> None:
    description = COLUMN_DESCRIPTIONS["tasks"]["status"]

    assert "done" in description
    assert "已完成" in description
    assert "未完成" in description
