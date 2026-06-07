import re
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.db.database import engine
from app.services.embedding_client import EmbeddingClient, create_embedding_client
from app.services.schema_document_service import TABLE_BUSINESS_TERMS, SchemaDocumentService
from app.services.schema_service import SchemaService
from app.services.table_data_safety import qualified_table_name, quote_identifier
from app.services.vector_store import VectorStoreService


TEXT_VALUE_TYPE_MARKERS = ("char", "text", "uuid")
MAX_VALUE_MATCH_TABLES = 40
MAX_VALUE_MATCH_COLUMNS = 8
MAX_VALUE_MATCH_TERMS = 6
VALUE_MATCH_MIN_TERM_LENGTH = 2

VALUE_QUERY_STOPWORDS = {
    "什么",
    "哪个",
    "哪些",
    "多少",
    "平均",
    "合计",
    "总数",
    "数量",
    "查询",
    "查找",
    "显示",
    "列出",
    "的",
    "是",
    "有",
    "人",
    "吗",
    "和",
    "与",
    "what",
    "which",
    "who",
    "avg",
    "average",
    "sum",
    "total",
    "count",
}

SCHEMA_SEMANTIC_ALIASES: dict[str, set[str]] = {
    "平均": {"avg", "average", "mean"},
    "均值": {"avg", "average", "mean"},
    "气温": {"temp", "temperature"},
    "温度": {"temp", "temperature"},
    "摄氏": {"c", "celsius", "centigrade"},
    "华氏": {"f", "fahrenheit"},
    "地方": {"place", "location", "region", "area", "country", "province", "city", "district"},
    "地点": {"place", "location", "region", "area", "country", "province", "city", "district"},
    "地区": {"region", "area", "country", "province", "city", "district"},
    "城市": {"city"},
    "省份": {"province", "state"},
    "省": {"province", "state"},
    "国家": {"country"},
    "区": {"district", "area"},
    "数量": {"count", "number", "quantity"},
    "数目": {"count", "number", "quantity"},
    "个数": {"count", "number", "quantity"},
    "人数": {"count", "number", "people", "person"},
    "金额": {"amount", "money", "revenue", "price", "cost"},
    "收入": {"revenue", "income", "amount"},
    "营收": {"revenue", "income", "amount"},
    "费用": {"cost", "expense", "amount"},
    "价格": {"price", "amount"},
    "成本": {"cost", "amount"},
    "乘客": {"passenger", "traveler", "pax", "count"},
    "旅客": {"passenger", "traveler", "pax", "count"},
    "载客": {"passenger", "traveler", "pax", "count"},
    "客量": {"passenger", "traveler", "pax", "count"},
    "时长": {"duration", "minutes", "hours", "time"},
    "分钟": {"minute", "minutes", "duration"},
    "小时": {"hour", "hours", "duration"},
    "延迟": {"delay", "late", "minutes"},
    "迟到": {"delay", "late", "minutes"},
    "员工": {"employee", "staff", "user", "person"},
    "人员": {"employee", "staff", "user", "person"},
    "用户": {"user", "employee", "person"},
    "设备": {"device", "equipment", "machine"},
    "机器": {"machine", "equipment", "device"},
    "机械": {"machine", "equipment", "device"},
    "日期": {"date", "day"},
    "时间": {"time", "datetime", "timestamp"},
}

SCHEMA_SEMANTIC_MIN_SCORE = 18


class SchemaRetriever:
    def __init__(
        self,
        schema_service: SchemaService | None = None,
        document_service: SchemaDocumentService | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: VectorStoreService | None = None,
        value_matcher: Any | None = None,
    ) -> None:
        self.schema_service = schema_service or SchemaService()
        self.document_service = document_service or SchemaDocumentService(self.schema_service)
        self.embedding_client = embedding_client or create_embedding_client()
        self.vector_store = vector_store or VectorStoreService()
        self.value_matcher = value_matcher or SchemaValueMatcher(self.schema_service)

    def index_schema(self, refresh: bool = False, reset: bool = True) -> dict[str, int]:
        documents = self.document_service.build_documents(refresh=refresh)
        embeddings = self.embedding_client.embed_texts([document["content"] for document in documents])

        if reset:
            self.vector_store.reset_collection()

        inserted = self.vector_store.upsert_documents(documents, embeddings)
        return {
            "documents": len(documents),
            "inserted": inserted,
        }

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        refresh_index: bool = False,
        use_keyword_fallback: bool = True,
        preferred_table_names: list[str] | None = None,
        restrict_to_preferred: bool = False,
    ) -> dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        preferred_tables = self._known_table_names(preferred_table_names or [])
        if restrict_to_preferred:
            return {
                "question": normalized_question,
                "matches": self._merge_matches(self._selected_scope_matches(preferred_tables), top_k),
            }

        if refresh_index or self._collection_is_empty():
            self.index_schema(refresh=refresh_index, reset=True)

        query_embedding = self.embedding_client.embed_text(normalized_question)
        vector_matches = self._search_with_reindex_retry(query_embedding, top_k)

        matches = [self._build_vector_match(result) for result in vector_matches]
        if use_keyword_fallback:
            matches.extend(self._keyword_matches(normalized_question))
            matches.extend(self._semantic_matches(normalized_question))
            matches.extend(self._value_matches(normalized_question))
        if preferred_tables:
            matches.extend(self._selected_scope_matches(preferred_tables))

        return {
            "question": normalized_question,
            "matches": self._merge_matches(matches, top_k),
        }

    def _collection_is_empty(self) -> bool:
        try:
            return self.vector_store.count_documents() == 0
        except Exception:
            return True

    def _search_with_reindex_retry(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        search_limit = max(top_k * 3, top_k)
        try:
            return self.vector_store.similarity_search(query_embedding, top_k=search_limit)
        except Exception:
            self.index_schema(refresh=True, reset=True)
            return self.vector_store.similarity_search(query_embedding, top_k=search_limit)

    def _build_vector_match(self, result: dict[str, Any]) -> dict[str, Any]:
        metadata = result.get("metadata") or {}
        table_name = metadata.get("table_name") or self._table_name_from_id(result.get("id", ""))
        distance = result.get("distance")
        return {
            "table_name": table_name,
            "columns": self._column_names(table_name),
            "score": self._distance_to_score(distance),
            "distance": distance,
            "source": "vector",
            "content": result.get("content", ""),
        }

    def _keyword_matches(self, question: str) -> list[dict[str, Any]]:
        question_lower = question.lower()
        matches = []

        for document in self.document_service.build_documents():
            table_name = document["table_name"]
            terms = [table_name, *TABLE_BUSINESS_TERMS.get(table_name, []), *document.get("columns", [])]
            matched_terms = {
                term.lower()
                for term in terms
                if term and term.lower() in question_lower
            }

            if not matched_terms:
                continue

            matches.append(
                {
                    "table_name": table_name,
                    "columns": self._column_names(table_name),
                    "score": min(0.95, 0.65 + len(matched_terms) * 0.05),
                    "distance": None,
                    "source": "keyword",
                    "content": document["content"],
                }
            )

        return matches

    def _value_matches(self, question: str) -> list[dict[str, Any]]:
        try:
            return self.value_matcher.match(question)
        except Exception:
            return []

    def _semantic_matches(self, question: str) -> list[dict[str, Any]]:
        question_terms = self._semantic_terms(question)
        if not question_terms:
            return []

        matches = []
        for document in self.document_service.build_documents():
            table_name = document["table_name"]
            table_schema = self.schema_service.get_table_schema(table_name)
            if not table_schema:
                continue

            table_terms = self._semantic_terms(self._semantic_table_text(table_schema, document))
            overlap = question_terms & table_terms
            score_points = len(overlap) * 5

            lowered_question = question.lower()
            for alias, expansions in SCHEMA_SEMANTIC_ALIASES.items():
                if alias in lowered_question and (expansions & table_terms):
                    score_points += 10

            if score_points < SCHEMA_SEMANTIC_MIN_SCORE:
                continue

            matches.append(
                {
                    "table_name": table_name,
                    "columns": self._column_names(table_name),
                    "score": min(0.94, 0.7 + score_points / 100),
                    "distance": None,
                    "source": "semantic",
                    "content": document["content"],
                }
            )

        return matches

    def _selected_scope_matches(self, table_names: list[str]) -> list[dict[str, Any]]:
        documents_by_table = {
            document["table_name"]: document
            for document in self.document_service.build_documents()
        }
        matches = []
        for table_name in table_names:
            document = documents_by_table.get(table_name)
            table_schema = self.schema_service.get_table_schema(table_name)
            if not document or not table_schema:
                continue

            matches.append(
                {
                    "table_name": table_name,
                    "columns": [column["name"] for column in table_schema.get("columns", [])],
                    "score": 1.0,
                    "distance": None,
                    "source": "selected_scope",
                    "content": document["content"],
                }
            )
        return matches

    def _merge_matches(self, matches: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}

        for match in matches:
            table_name = match["table_name"]
            existing = merged.get(table_name)
            if existing is None:
                merged[table_name] = match
                continue

            existing["score"] = max(existing["score"], match["score"])
            existing["source"] = self._merge_sources(existing["source"], match["source"])
            existing["content"] = existing["content"] or match["content"]
            existing["distance"] = self._best_distance(existing.get("distance"), match.get("distance"))

        sorted_matches = sorted(
            merged.values(),
            key=lambda item: (item["score"], item["table_name"]),
            reverse=True,
        )
        for match in sorted_matches:
            match["score"] = round(match["score"], 6)
        return sorted_matches[:top_k]

    def _column_names(self, table_name: str) -> list[str]:
        table_schema = self.schema_service.get_table_schema(table_name)
        if table_schema is None:
            return []
        return [column["name"] for column in table_schema.get("columns", [])]

    def _known_table_names(self, table_names: list[str]) -> list[str]:
        if not table_names:
            return []
        available_tables = {table["name"] for table in self.schema_service.list_tables()}
        known_tables = []
        for table_name in table_names:
            normalized_table_name = str(table_name or "").strip()
            if normalized_table_name and normalized_table_name in available_tables and normalized_table_name not in known_tables:
                known_tables.append(normalized_table_name)
        return known_tables

    def _table_name_from_id(self, document_id: str) -> str:
        return document_id.rsplit(":", maxsplit=1)[-1]

    def _semantic_table_text(self, table_schema: dict[str, Any], document: dict[str, Any]) -> str:
        parts = [
            str(table_schema.get("name") or ""),
            str(table_schema.get("description") or ""),
            str(document.get("content") or ""),
        ]
        for column in table_schema.get("columns", []):
            parts.append(str(column.get("name") or ""))
            parts.append(str(column.get("description") or ""))
            parts.append(str(column.get("type") or ""))
        return " ".join(parts)

    def _semantic_terms(self, text_value: str) -> set[str]:
        lowered = text_value.lower()
        terms = set(re.findall(r"[a-z0-9]+", lowered))
        for cjk_part in re.findall(r"[\u4e00-\u9fff]+", lowered):
            terms.add(cjk_part)
            if len(cjk_part) >= 2:
                terms.update(cjk_part[index : index + 2] for index in range(len(cjk_part) - 1))

        for alias, expansions in SCHEMA_SEMANTIC_ALIASES.items():
            if alias in lowered:
                terms.add(alias)
                terms.update(expansions)
        return {term for term in terms if term}

    def _distance_to_score(self, distance: float | None) -> float:
        if distance is None:
            return 0.0
        return 1.0 / (1.0 + max(float(distance), 0.0))

    def _merge_sources(self, first: str, second: str) -> str:
        return "+".join(sorted({*first.split("+"), *second.split("+")}))

    def _best_distance(self, first: float | None, second: float | None) -> float | None:
        if first is None:
            return second
        if second is None:
            return first
        return min(first, second)


class SchemaValueMatcher:
    def __init__(
        self,
        schema_service: SchemaService,
        db_engine: Any | None = None,
        schema_name: str | None = None,
    ) -> None:
        self.schema_service = schema_service
        self.db_engine = db_engine or engine
        self.schema_name = schema_name or settings.db_schema

    def match(self, question: str, table_names: list[str] | None = None) -> list[dict[str, Any]]:
        terms = self._extract_value_terms(question)
        if not terms:
            return []

        candidate_tables = table_names or [
            table["name"]
            for table in self.schema_service.list_tables()
            if table.get("name")
        ]
        matches = []
        for table_name in candidate_tables[:MAX_VALUE_MATCH_TABLES]:
            table_schema = self.schema_service.get_table_schema(table_name)
            if not table_schema:
                continue

            text_columns = self._text_columns(table_schema)
            if not text_columns:
                continue

            matched = self._table_has_value_match(table_name, text_columns, terms)
            if not matched:
                continue

            matches.append(
                {
                    "table_name": table_name,
                    "columns": [column["name"] for column in table_schema.get("columns", [])],
                    "score": 0.96,
                    "distance": None,
                    "source": "value",
                    "content": self._content_for_table(table_schema),
                }
            )

        return matches

    def _table_has_value_match(self, table_name: str, text_columns: list[str], terms: list[str]) -> bool:
        clauses = []
        params: dict[str, Any] = {}
        parameter_index = 0
        for term in terms[:MAX_VALUE_MATCH_TERMS]:
            pattern = self._like_pattern(term)
            for column_name in text_columns[:MAX_VALUE_MATCH_COLUMNS]:
                parameter_name = f"pattern_{parameter_index}"
                clauses.append(f"CAST({quote_identifier(column_name)} AS TEXT) ILIKE :{parameter_name} ESCAPE '!'")
                params[parameter_name] = pattern
                parameter_index += 1

        if not clauses:
            return False

        sql = (
            f"SELECT 1 FROM {qualified_table_name(self.schema_name, table_name)} "
            f"WHERE {' OR '.join(clauses)} "
            "LIMIT 1"
        )
        try:
            with self.db_engine.connect() as connection:
                timeout_ms = max(int(settings.sql_statement_timeout_ms), 1)
                connection.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                return connection.execute(text(sql), params).first() is not None
        except Exception:
            return False

    def _extract_value_terms(self, question: str) -> list[str]:
        lowered = question.lower()
        terms: list[str] = []

        for match in re.findall(r"[a-z0-9][a-z0-9_-]*", lowered):
            self._append_term(terms, match)

        for cjk_part in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
            self._append_term(terms, cjk_part)
            cleaned_cjk_part = self._strip_cjk_question_words(cjk_part)
            self._append_term(terms, cleaned_cjk_part)
            max_window = min(5, len(cjk_part))
            for window_size in range(max_window, 1, -1):
                for index in range(0, len(cjk_part) - window_size + 1):
                    self._append_term(terms, cjk_part[index : index + window_size])

        return terms[:MAX_VALUE_MATCH_TERMS]

    def _strip_cjk_question_words(self, value: str) -> str:
        cleaned = value
        for stopword in sorted(VALUE_QUERY_STOPWORDS, key=len, reverse=True):
            if re.fullmatch(r"[\u4e00-\u9fff]+", stopword):
                cleaned = cleaned.replace(stopword, "")
        return cleaned

    def _append_term(self, terms: list[str], term: str) -> None:
        cleaned = term.strip().strip("_-")
        if not cleaned or cleaned in terms:
            return
        if len(cleaned) < VALUE_MATCH_MIN_TERM_LENGTH:
            return
        if cleaned in VALUE_QUERY_STOPWORDS:
            return
        if cleaned.isdigit():
            return
        terms.append(cleaned)

    def _text_columns(self, table_schema: dict[str, Any]) -> list[str]:
        columns = []
        for column in table_schema.get("columns", []):
            column_name = str(column.get("name") or "")
            column_type = str(column.get("type") or "").lower()
            if column_name and any(marker in column_type for marker in TEXT_VALUE_TYPE_MARKERS):
                columns.append(column_name)
        return columns

    def _content_for_table(self, table_schema: dict[str, Any]) -> str:
        column_names = ", ".join(column["name"] for column in table_schema.get("columns", []) if column.get("name"))
        return f"Table: {table_schema.get('name')}\nDescription: {table_schema.get('description', '')}\nColumns: {column_names}"

    def _like_pattern(self, term: str) -> str:
        escaped = term.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("'", "''")
        return f"%{escaped}%"
