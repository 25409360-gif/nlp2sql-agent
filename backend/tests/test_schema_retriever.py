import unittest

from app.services.schema_retriever import SchemaRetriever, SchemaValueMatcher


class FakeSchemaService:
    def list_tables(self):
        return [
            {"name": "airport_operations_dirty_35_rows"},
            {"name": "china_temperature_distribution_150_rows"},
            {"name": "users"},
        ]

    def get_table_schema(self, table_name):
        schemas = {
            "airport_operations_dirty_35_rows": {
                "name": "airport_operations_dirty_35_rows",
                "description": "Imported from file: airport_operations_dirty_35_rows.xlsx",
                "columns": [
                    {"name": "aircraft_type", "type": "TEXT"},
                    {"name": "passenger_count", "type": "BIGINT"},
                ],
                "foreign_keys": [],
            },
            "users": {
                "name": "users",
                "description": "users table",
                "columns": [
                    {"name": "id", "type": "INTEGER"},
                    {"name": "name", "type": "TEXT"},
                ],
                "foreign_keys": [],
            },
            "china_temperature_distribution_150_rows": {
                "name": "china_temperature_distribution_150_rows",
                "description": "Imported from file: china_temperature_distribution_150_rows.xlsx",
                "columns": [
                    {"name": "country", "type": "TEXT"},
                    {"name": "province", "type": "TEXT"},
                    {"name": "city", "type": "TEXT"},
                    {"name": "district", "type": "TEXT"},
                    {"name": "avg_temp_c", "type": "NUMERIC"},
                ],
                "foreign_keys": [],
            },
        }
        return schemas.get(table_name)


class FakeDocumentService:
    def build_documents(self, refresh=False):
        return [
            {
                "table_name": "airport_operations_dirty_35_rows",
                "columns": ["aircraft_type", "passenger_count"],
                "content": "Table: airport_operations_dirty_35_rows\nColumns: aircraft_type, passenger_count",
            },
            {
                "table_name": "users",
                "columns": ["id", "name"],
                "content": "Table: users\nColumns: id, name",
            },
            {
                "table_name": "china_temperature_distribution_150_rows",
                "columns": ["country", "province", "city", "district", "avg_temp_c"],
                "content": (
                    "Table: china_temperature_distribution_150_rows\n"
                    "Columns: country, province, city, district, avg_temp_c"
                ),
            },
        ]


class FakeEmbeddingClient:
    def embed_text(self, text):
        return [0.0, 1.0]

    def embed_texts(self, texts):
        return [[0.0, 1.0] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.search_calls = 0

    def count_documents(self):
        return 1

    def similarity_search(self, query_embedding, top_k=5):
        self.search_calls += 1
        return []

    def reset_collection(self):
        return None

    def upsert_documents(self, documents, embeddings):
        return len(documents)


class FakeValueMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def match(self, question):
        self.calls += 1
        if "B787" not in question:
            return []
        return [
            {
                "table_name": "airport_operations_dirty_35_rows",
                "columns": ["aircraft_type", "passenger_count"],
                "score": 0.9,
                "distance": None,
                "source": "value",
                "content": "B787 matched in aircraft_type",
            }
        ]


class SchemaRetrieverTest(unittest.TestCase):
    def make_retriever(self, vector_store=None, value_matcher=None):
        return SchemaRetriever(
            schema_service=FakeSchemaService(),
            document_service=FakeDocumentService(),
            embedding_client=FakeEmbeddingClient(),
            vector_store=vector_store or FakeVectorStore(),
            value_matcher=value_matcher or FakeValueMatcher(),
        )

    def test_value_match_finds_table_when_question_contains_data_value(self) -> None:
        value_matcher = FakeValueMatcher()
        retriever = self.make_retriever(value_matcher=value_matcher)

        result = retriever.retrieve("B787的平均载客量多少", top_k=5)

        self.assertEqual(value_matcher.calls, 1)
        self.assertEqual(result["matches"][0]["table_name"], "airport_operations_dirty_35_rows")
        self.assertIn("value", result["matches"][0]["source"])

    def test_restricted_preferred_table_skips_global_search(self) -> None:
        vector_store = FakeVectorStore()
        value_matcher = FakeValueMatcher()
        retriever = self.make_retriever(vector_store=vector_store, value_matcher=value_matcher)

        result = retriever.retrieve(
            "B787的平均载客量多少",
            top_k=5,
            preferred_table_names=["airport_operations_dirty_35_rows"],
            restrict_to_preferred=True,
        )

        self.assertEqual(vector_store.search_calls, 0)
        self.assertEqual(value_matcher.calls, 0)
        self.assertEqual([match["table_name"] for match in result["matches"]], ["airport_operations_dirty_35_rows"])
        self.assertEqual(result["matches"][0]["source"], "selected_scope")

    def test_semantic_match_finds_uploaded_table_by_metric_meaning(self) -> None:
        retriever = self.make_retriever()

        result = retriever.retrieve("有哪些地方平均气温低于25摄氏度", top_k=5)

        self.assertEqual(result["matches"][0]["table_name"], "china_temperature_distribution_150_rows")
        self.assertIn("semantic", result["matches"][0]["source"])

    def test_value_term_extraction_handles_codes_and_chinese_values(self) -> None:
        matcher = SchemaValueMatcher(FakeSchemaService(), db_engine=object())

        self.assertIn("b787", matcher._extract_value_terms("B787的平均载客量多少"))
        self.assertIn("研发部", matcher._extract_value_terms("研发部有多少人"))


if __name__ == "__main__":
    unittest.main()
