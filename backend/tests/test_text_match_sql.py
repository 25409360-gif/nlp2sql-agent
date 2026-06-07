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
            "china_temperature_distribution_150_rows": {
                "name": "china_temperature_distribution_150_rows",
                "description": "Imported from file: china_temperature_distribution_150_rows.xlsx",
                "columns": [
                    {
                        "name": "record_id",
                        "type": "TEXT",
                        "description": "Original column: record_id; inferred type: text",
                    },
                    {
                        "name": "province",
                        "type": "TEXT",
                        "description": "Original column: province; inferred type: text",
                    },
                    {
                        "name": "city",
                        "type": "TEXT",
                        "description": "Original column: city; inferred type: text",
                    },
                    {
                        "name": "district",
                        "type": "TEXT",
                        "description": "Original column: district; inferred type: text",
                    },
                    {
                        "name": "station_id",
                        "type": "TEXT",
                        "description": "Original column: station_id; inferred type: text",
                    },
                    {
                        "name": "latitude",
                        "type": "NUMERIC",
                        "description": "Original column: latitude; inferred type: numeric",
                    },
                    {
                        "name": "longitude",
                        "type": "NUMERIC",
                        "description": "Original column: longitude; inferred type: numeric",
                    },
                    {
                        "name": "avg_temp_c",
                        "type": "NUMERIC",
                        "description": "Original column: avg_temp_c; inferred type: numeric",
                    },
                    {
                        "name": "max_temp_c",
                        "type": "NUMERIC",
                        "description": "Original column: max_temp_c; inferred type: numeric",
                    },
                    {
                        "name": "min_temp_c",
                        "type": "NUMERIC",
                        "description": "Original column: min_temp_c; inferred type: numeric",
                    },
                    {
                        "name": "humidity_percent",
                        "type": "NUMERIC",
                        "description": "Original column: humidity_percent; inferred type: numeric",
                    },
                    {
                        "name": "wind_speed_kmh",
                        "type": "INTEGER",
                        "description": "Original column: wind_speed_kmh; inferred type: integer",
                    },
                ],
                "primary_keys": [],
                "foreign_keys": [],
            },
            "employee_compensation_upload": {
                "name": "employee_compensation_upload",
                "description": "Imported employee compensation table.",
                "columns": [
                    {
                        "name": "department",
                        "type": "TEXT",
                        "description": "Original column: Department; inferred type: text",
                    },
                    {
                        "name": "employee_name",
                        "type": "TEXT",
                        "description": "Original column: Employee Name; inferred type: text",
                    },
                    {
                        "name": "salary",
                        "type": "NUMERIC",
                        "description": "Original column: Salary; inferred type: numeric",
                    },
                    {
                        "name": "overtime_hours",
                        "type": "NUMERIC",
                        "description": "Original column: Overtime Hours; inferred type: numeric",
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
    {
        "table_name": "china_temperature_distribution_150_rows",
        "columns": [
            "record_id",
            "province",
            "city",
            "district",
            "station_id",
            "latitude",
            "longitude",
            "avg_temp_c",
            "max_temp_c",
            "min_temp_c",
            "humidity_percent",
            "wind_speed_kmh",
        ],
        "content": (
            "Imported temperature table. Columns: province, city, district, station_id, "
            "latitude, longitude, avg_temp_c, max_temp_c, min_temp_c, humidity_percent, wind_speed_kmh."
        ),
        "source": "semantic",
        "score": 0.94,
    },
    {
        "table_name": "employee_compensation_upload",
        "columns": ["department", "employee_name", "salary", "overtime_hours"],
        "content": "Imported employee compensation table. Columns: department, employee_name, salary, overtime_hours.",
        "source": "semantic",
        "score": 0.94,
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

    def test_grouped_average_ranking_by_aircraft_type(self) -> None:
        result = self.builder.build(
            question="哪个型号的飞机平均载客量最大",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": ["airport_operations_dirty_35_rows"], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "airport_operations_dirty_35_rows")
        self.assertEqual(result["metric_column"], "passenger_count")
        self.assertIn("aod.aircraft_type", result["sql"])
        self.assertIn("AVG(aod.passenger_count) AS average_passenger_count", result["sql"])
        self.assertIn("GROUP BY aod.aircraft_type", result["sql"])
        self.assertIn("ORDER BY average_passenger_count DESC", result["sql"])
        self.assertIn("LIMIT 1", result["sql"])
        self.assertNotIn("ILIKE '%型号%'", result["sql"])
        self.assertNotIn("aod.flight_no", result["sql"])

    def test_grouped_average_ranking_works_for_employee_table(self) -> None:
        result = self.builder.build(
            question="哪个部门平均工资最高",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "employee_compensation_upload")
        self.assertEqual(result["metric_column"], "salary")
        self.assertIn("ecu.department", result["sql"])
        self.assertIn("AVG(ecu.salary) AS average_salary", result["sql"])
        self.assertIn("GROUP BY ecu.department", result["sql"])
        self.assertIn("ORDER BY average_salary DESC", result["sql"])
        self.assertIn("LIMIT 1", result["sql"])
        self.assertNotIn("ecu.employee_name", result["sql"])

    def test_grouped_average_ranking_lowest_works_for_employee_table(self) -> None:
        result = self.builder.build(
            question="哪个部门平均工资最低",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "employee_compensation_upload")
        self.assertEqual(result["metric_column"], "salary")
        self.assertIn("ecu.department", result["sql"])
        self.assertIn("AVG(ecu.salary) AS average_salary", result["sql"])
        self.assertIn("GROUP BY ecu.department", result["sql"])
        self.assertIn("ORDER BY average_salary ASC", result["sql"])
        self.assertIn("LIMIT 1", result["sql"])
        self.assertNotIn("ecu.employee_name", result["sql"])

    def test_grouped_average_ranking_respects_top_n_limit(self) -> None:
        result = self.builder.build(
            question="前3个型号的飞机平均载客量最大",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": ["airport_operations_dirty_35_rows"], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertIn("GROUP BY aod.aircraft_type", result["sql"])
        self.assertIn("ORDER BY average_passenger_count DESC", result["sql"])
        self.assertIn("LIMIT 3", result["sql"])

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

    def test_grouped_semantic_average_with_numeric_comparison(self) -> None:
        result = self.builder.build(
            question="有哪些地方平均气温低于25摄氏度",
            intent_result={
                "intent_type": "simple_lookup",
                "entities": {"tables": [], "metrics": [], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "china_temperature_distribution_150_rows")
        self.assertEqual(result["metric_column"], "avg_temp_c")
        self.assertIn("AVG(ctd.avg_temp_c) AS average_avg_temp_c", result["sql"])
        self.assertIn("GROUP BY", result["sql"])
        self.assertIn("HAVING AVG(ctd.avg_temp_c) < 25", result["sql"])
        self.assertIn("ctd.city", result["sql"])
        self.assertIn("ctd.district", result["sql"])
        self.assertNotIn("station_id", result["sql"])
        self.assertNotIn("latitude", result["metric_column"])

    def test_where_average_temperature_lowest_groups_by_location(self) -> None:
        result = self.builder.build(
            question="哪里的平均气温最低",
            intent_result={
                "intent_type": "ranking_query",
                "entities": {"tables": ["china_temperature_distribution_150_rows"], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "china_temperature_distribution_150_rows")
        self.assertEqual(result["metric_column"], "avg_temp_c")
        self.assertEqual(result["terms"], [])
        self.assertIn("AVG(ctd.avg_temp_c) AS average_avg_temp_c", result["sql"])
        self.assertIn("GROUP BY", result["sql"])
        self.assertIn("ORDER BY average_avg_temp_c ASC", result["sql"])
        self.assertIn("LIMIT 1", result["sql"])
        self.assertNotIn("min_temp_c", result["sql"])
        self.assertNotIn("ILIKE '%哪里%'", result["sql"])

    def test_statistical_qualifier_maps_max_temperature_column(self) -> None:
        result = self.builder.build(
            question="有哪些地方最高气温高于30摄氏度",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": [], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "china_temperature_distribution_150_rows")
        self.assertEqual(result["metric_column"], "max_temp_c")
        self.assertIn("MAX(ctd.max_temp_c) AS maximum_max_temp_c", result["sql"])
        self.assertIn("HAVING MAX(ctd.max_temp_c) > 30", result["sql"])

    def test_question_text_overrides_noisy_llm_metric_for_max_temperature(self) -> None:
        result = self.builder.build(
            question="有哪些地方最高气温高于30摄氏度",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metric_column"], "max_temp_c")
        self.assertIn("MAX(ctd.max_temp_c)", result["sql"])
        self.assertNotIn("AVG(ctd.max_temp_c)", result["sql"])

    def test_statistical_qualifier_maps_min_temperature_column(self) -> None:
        result = self.builder.build(
            question="有哪些地方最低气温低于10摄氏度",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": [], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "china_temperature_distribution_150_rows")
        self.assertEqual(result["metric_column"], "min_temp_c")
        self.assertIn("MIN(ctd.min_temp_c) AS minimum_min_temp_c", result["sql"])
        self.assertIn("HAVING MIN(ctd.min_temp_c) < 10", result["sql"])

    def test_average_humidity_uses_humidity_not_temperature_or_coordinates(self) -> None:
        result = self.builder.build(
            question="哪些地方平均湿度高于70",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": [], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["table_name"], "china_temperature_distribution_150_rows")
        self.assertEqual(result["metric_column"], "humidity_percent")
        self.assertIn("AVG(ctd.humidity_percent) AS average_humidity_percent", result["sql"])
        self.assertNotIn("AVG(ctd.latitude)", result["sql"])
        self.assertNotIn("AVG(ctd.avg_temp_c)", result["sql"])

    def test_statistical_word_alone_still_requires_metric_clarification(self) -> None:
        result = self.builder.build(
            question="哪些地方平均数低于25",
            intent_result={
                "intent_type": "aggregate_query",
                "entities": {"tables": [], "metrics": ["average"], "filters": []},
            },
            schema_context=SCHEMA_CONTEXT,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("avg_temp_c", result["reason"])
        self.assertIn("humidity_percent", result["reason"])


if __name__ == "__main__":
    unittest.main()
