import unittest

from app.agent.text_match_sql import TextMatchSQLBuilder


class FakeSchemaService:
    def get_table_schema(self, table_name):
        schemas = {
            "attendance_records": {
                "name": "attendance_records",
                "description": "考勤记录表，记录用户每日打卡、工时和出勤状态。",
                "columns": [
                    {"name": "id", "type": "INTEGER", "description": "考勤记录 ID"},
                    {"name": "status", "type": "VARCHAR(40)", "description": "出勤状态"},
                ],
                "primary_keys": ["id"],
                "foreign_keys": [],
            },
            "departments": {
                "name": "departments",
                "description": "部门信息表，记录企业或实验室内部的组织部门。",
                "columns": [
                    {"name": "id", "type": "INTEGER", "description": "部门 ID"},
                    {"name": "name", "type": "VARCHAR(120)", "description": "部门名称"},
                    {"name": "description", "type": "TEXT", "description": "部门说明"},
                    {"name": "created_at", "type": "TIMESTAMP", "description": "创建时间"},
                ],
                "primary_keys": ["id"],
                "foreign_keys": [],
            },
            "airport_operations_dirty_35_rows": {
                "name": "airport_operations_dirty_35_rows",
                "description": "Imported from file: airport_operations_dirty_35_rows.xlsx",
                "columns": [
                    {
                        "name": "flight_no",
                        "type": "TEXT",
                        "description": "Original column: Flight No; inferred type: text",
                    },
                    {
                        "name": "aircraft_type",
                        "type": "TEXT",
                        "description": "Original column: Aircraft Type; inferred type: text",
                    },
                    {
                        "name": "delay_minutes",
                        "type": "BIGINT",
                        "description": "Original column: Delay Minutes; inferred type: integer",
                    },
                    {
                        "name": "passenger_count",
                        "type": "BIGINT",
                        "description": "Original column: Passenger Count; inferred type: integer",
                    },
                    {
                        "name": "revenue_hkd",
                        "type": "NUMERIC",
                        "description": "Original column: Revenue HKD; inferred type: numeric",
                    },
                ],
                "primary_keys": [],
                "foreign_keys": [],
            },
        }
        return schemas.get(table_name)


SCHEMA_CONTEXT = [
    {
        "table_name": "attendance_records",
        "columns": ["id", "status"],
        "content": "考勤记录表，记录用户每日打卡、工时和出勤状态。",
    },
    {
        "table_name": "departments",
        "columns": ["id", "name", "description", "created_at"],
        "content": "部门信息表，记录企业或实验室内部的组织部门。",
    },
    {
        "table_name": "airport_operations_dirty_35_rows",
        "columns": ["flight_no", "aircraft_type", "delay_minutes", "passenger_count", "revenue_hkd"],
        "content": (
            "Imported airport operations table. Columns: aircraft_type, delay_minutes, "
            "passenger_count, revenue_hkd."
        ),
    },
]


class TextMatchSQLBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = TextMatchSQLBuilder(FakeSchemaService())

    def test_builds_partial_description_lookup_for_target_table(self) -> None:
        result = self.builder.build(
            question="负责前端研发的是什么部门",
            intent_result={
                "intent_type": "simple_lookup",
                "entities": {"tables": ["attendance_records", "departments"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["table_name"], "departments")
        self.assertEqual(result["terms"], ["前端", "研发"])
        self.assertEqual(result["threshold"], 2)
        self.assertIn("ILIKE '%前端%'", result["sql"])
        self.assertIn("ILIKE '%研发%'", result["sql"])

    def test_full_description_lookup_uses_distinct_terms_not_duplicate_columns(self) -> None:
        result = self.builder.build(
            question="负责后端、前端、平台和业务系统研发是什么部门",
            intent_result={
                "intent_type": "simple_lookup",
                "entities": {"tables": ["departments"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["terms"], ["后端", "前端", "平台", "业务", "系统", "研发"])
        self.assertEqual(result["threshold"], 4)
        self.assertNotIn("、前", result["terms"])
        self.assertEqual(result["sql"].count("CASE WHEN"), len(result["terms"]) * 2)

    def test_data_platform_keeps_data_as_content_term(self) -> None:
        result = self.builder.build(
            question="数据平台是什么部门",
            intent_result={
                "intent_type": "simple_lookup",
                "entities": {"tables": ["departments"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["terms"], ["数据", "平台"])
        self.assertEqual(result["threshold"], 2)

    def test_english_terms_are_not_split_inside_words(self) -> None:
        terms = self.builder._extract_terms(
            "which department handles error monitoring",
            [{"table_name": "departments"}],
        )

        self.assertIn("error", terms)
        self.assertIn("monitoring", terms)
        self.assertNotIn("err", terms)

    def test_ranking_questions_still_use_llm_sql_generation(self) -> None:
        result = self.builder.build(
            question="谁迟到次数最多？",
            intent_result={
                "intent_type": "ranking_query",
                "entities": {"tables": ["attendance_records", "users"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNone(result)

    def test_semantic_average_maps_metric_column_in_multi_numeric_table(self) -> None:
        result = self.builder.build(
            question="B787的平均载客量多少",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": ["airport_operations_dirty_35_rows"], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["source"], "semantic_aggregate")
        self.assertEqual(result["table_name"], "airport_operations_dirty_35_rows")
        self.assertEqual(result["metric_column"], "passenger_count")
        self.assertEqual(result["terms"], ["b787"])
        self.assertIn("AVG(aod.passenger_count) AS average_passenger_count", result["sql"])
        self.assertIn("CAST(aod.aircraft_type AS TEXT) ILIKE '%b787%'", result["sql"])
        self.assertNotIn("AVG(aod.delay_minutes)", result["sql"])
        self.assertNotIn("AVG(aod.revenue_hkd)", result["sql"])

    def test_value_matched_table_is_not_crowded_out_by_wrong_intent_tables(self) -> None:
        result = self.builder.build(
            question="B787的平均载客量多少",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {
                    "tables": ["attendance_records", "departments", "users"],
                    "metrics": ["average"],
                    "filters": [],
                },
            },
            schema_context=[
                SCHEMA_CONTEXT[0],
                SCHEMA_CONTEXT[1],
                {
                    **SCHEMA_CONTEXT[2],
                    "source": "value",
                    "score": 0.96,
                },
            ],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "airport_operations_dirty_35_rows")
        self.assertEqual(result["metric_column"], "passenger_count")

    def test_semantic_average_requires_clarification_when_metric_is_ambiguous(self) -> None:
        result = self.builder.build(
            question="B787的平均数是多少",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": ["airport_operations_dirty_35_rows"], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("passenger_count", result["reason"])
        self.assertIn("delay_minutes", result["reason"])


if __name__ == "__main__":
    unittest.main()
