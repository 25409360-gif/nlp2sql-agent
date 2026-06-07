import unittest
from datetime import date, datetime, time
from decimal import Decimal

from app.services.table_data_safety import (
    InvalidPaginationError,
    InvalidTableNameError,
    UnknownTableError,
    build_table_count_sql,
    build_table_rows_sql,
    normalize_identifier,
    normalize_pagination,
    qualified_table_name,
    row_to_json_dict,
    to_json_safe,
    validate_table_name,
)


class TableDataSafetyTest(unittest.TestCase):
    def test_validates_existing_table_name(self) -> None:
        table_name = validate_table_name("users", ["attendance_records", "users"])

        self.assertEqual(table_name, "users")

    def test_rejects_unsafe_table_name(self) -> None:
        unsafe_names = ["public.users", "users;drop table users", "users-name", " users name "]

        for table_name in unsafe_names:
            with self.subTest(table_name=table_name):
                with self.assertRaises(InvalidTableNameError):
                    validate_table_name(table_name, ["users"])

    def test_rejects_unknown_table_name(self) -> None:
        with self.assertRaises(UnknownTableError):
            validate_table_name("orders", ["users"])

    def test_normalizes_pagination_defaults_and_caps_limit(self) -> None:
        default_pagination = normalize_pagination()
        capped_pagination = normalize_pagination(limit=500, offset=20)

        self.assertEqual(default_pagination.limit, 50)
        self.assertEqual(default_pagination.offset, 0)
        self.assertEqual(capped_pagination.limit, 100)
        self.assertEqual(capped_pagination.offset, 20)

    def test_rejects_invalid_pagination(self) -> None:
        with self.assertRaises(InvalidPaginationError):
            normalize_pagination(limit=0)

        with self.assertRaises(InvalidPaginationError):
            normalize_pagination(offset=-1)

        with self.assertRaises(InvalidPaginationError):
            normalize_pagination(limit="abc")

    def test_quotes_only_safe_identifiers(self) -> None:
        self.assertEqual(normalize_identifier("users"), "users")
        self.assertEqual(qualified_table_name("public", "users"), '"public"."users"')

        with self.assertRaises(InvalidTableNameError):
            qualified_table_name("public", 'users"')

    def test_builds_only_read_only_table_sql_templates(self) -> None:
        rows_sql = build_table_rows_sql("public", "users")
        count_sql = build_table_count_sql("public", "users")

        self.assertEqual(rows_sql, 'SELECT * FROM "public"."users" LIMIT :limit OFFSET :offset')
        self.assertEqual(
            build_table_rows_sql("public", "users", order_by=["id"]),
            'SELECT * FROM "public"."users" ORDER BY "id" LIMIT :limit OFFSET :offset',
        )
        self.assertEqual(count_sql, 'SELECT COUNT(*) AS total_count FROM "public"."users"')

        with self.assertRaises(InvalidTableNameError):
            build_table_rows_sql("public", "users;drop")

    def test_converts_values_to_json_safe_values(self) -> None:
        payload = {
            "none": None,
            "bool": True,
            "decimal": Decimal("12.34"),
            "decimal_nan": Decimal("NaN"),
            "datetime": datetime(2026, 6, 6, 15, 30, 0),
            "date": date(2026, 6, 6),
            "time": time(15, 30, 0),
            "bytes": b"abc",
            "float_nan": float("nan"),
            "nested": {"values": [Decimal("1.5"), b"x"]},
        }

        converted = to_json_safe(payload)

        self.assertEqual(converted["none"], None)
        self.assertEqual(converted["bool"], True)
        self.assertEqual(converted["decimal"], 12.34)
        self.assertEqual(converted["decimal_nan"], "NaN")
        self.assertEqual(converted["datetime"], "2026-06-06T15:30:00")
        self.assertEqual(converted["date"], "2026-06-06")
        self.assertEqual(converted["time"], "15:30:00")
        self.assertEqual(converted["bytes"], "616263")
        self.assertEqual(converted["float_nan"], "nan")
        self.assertEqual(converted["nested"], {"values": [1.5, "78"]})

    def test_converts_row_mapping_with_ordered_columns(self) -> None:
        row = {"id": 1, "score": Decimal("9.5"), "created_at": date(2026, 6, 6)}

        converted = row_to_json_dict(row, ["id", "score", "created_at"])

        self.assertEqual(converted, {"id": 1, "score": 9.5, "created_at": "2026-06-06"})


if __name__ == "__main__":
    unittest.main()
