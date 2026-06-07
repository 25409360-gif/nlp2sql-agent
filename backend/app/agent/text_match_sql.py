import re
from dataclasses import asdict, dataclass, field
from math import ceil
from typing import Any


TEXT_TYPE_MARKERS = ("char", "text", "json", "uuid")
NUMERIC_TYPE_MARKERS = ("int", "numeric", "decimal", "double", "real", "float")

QUESTION_STOPWORDS = {
    "什么",
    "哪个",
    "哪些",
    "哪一个",
    "是多少",
    "是什么",
    "是谁",
    "查询",
    "查找",
    "找出",
    "搜索",
    "筛选",
    "列出",
    "显示",
    "告诉我",
    "请问",
    "请",
    "一下",
    "相关",
    "对应",
    "信息",
    "记录",
    "名称",
    "名字",
    "描述",
    "说明",
    "包含",
    "包括",
    "负责",
    "属于",
    "里面",
    "中的",
    "里的",
    "的是",
    "的是哪个",
    "的是哪些",
    "的是什么",
    "是",
    "的",
    "和",
    "及",
    "与",
    "或",
    "the",
    "a",
    "an",
    "is",
    "are",
    "what",
    "which",
    "who",
    "find",
    "search",
    "show",
    "list",
    "contains",
    "include",
    "includes",
}

QUERY_TYPE_TERMS = {
    "部门",
    "用户",
    "员工",
    "成员",
    "项目",
    "任务",
    "设备",
    "会议",
    "表",
    "department",
    "user",
    "employee",
    "project",
    "task",
    "device",
    "meeting",
    "table",
}

NON_TEXT_LOOKUP_TERMS = {
    "最多",
    "最高",
    "最低",
    "最少",
    "排名",
    "平均",
    "合计",
    "总数",
    "数量",
    "多少",
    "趋势",
    "每日",
    "每周",
    "每月",
    "top",
    "rank",
    "average",
    "avg",
    "sum",
    "count",
}

LOOKUP_TERMS = {
    "什么",
    "哪个",
    "哪些",
    "是谁",
    "是什么",
    "查询",
    "查找",
    "找出",
    "搜索",
    "包含",
    "包括",
    "负责",
    "what",
    "which",
    "who",
    "find",
    "search",
    "contains",
}

AGGREGATE_AVERAGE_TERMS = {"平均", "均值", "average", "avg", "mean"}
AGGREGATE_SUM_TERMS = {"合计", "总和", "总额", "sum", "total"}
AGGREGATE_COUNT_TERMS = {"多少", "数量", "总数", "个数", "count", "number"}
AGGREGATE_CONTROL_TERMS = AGGREGATE_AVERAGE_TERMS | AGGREGATE_SUM_TERMS | AGGREGATE_COUNT_TERMS

IDENTIFIER_COLUMN_NAMES = {"id", "pk", "key"}

SEMANTIC_ALIASES: dict[str, set[str]] = {
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
    "工资": {"salary", "wage", "pay", "compensation"},
    "薪资": {"salary", "wage", "pay", "compensation"},
    "薪水": {"salary", "wage", "pay", "compensation"},
    "乘客": {"passenger", "traveler", "pax", "count"},
    "旅客": {"passenger", "traveler", "pax", "count"},
    "载客": {"passenger", "traveler", "pax", "count"},
    "客量": {"passenger", "traveler", "pax", "count"},
    "客流": {"passenger", "traveler", "traffic", "count"},
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
    "挖掘机": {"excavator", "machine", "equipment"},
    "航班": {"flight"},
    "班次": {"flight"},
    "日期": {"date", "day"},
    "时间": {"time", "datetime", "timestamp"},
}


@dataclass
class TextMatchSQLCandidate:
    sql: str
    table_name: str
    terms: list[str]
    text_columns: list[str]
    selected_columns: list[str]
    threshold: int
    reason: str
    source: str = "text_match"
    status: str = "success"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TextMatchSQLBuilder:
    schema_service: Any
    default_limit: int = 20
    max_tables: int = 3

    def build(
        self,
        question: str,
        intent_result: dict[str, Any],
        schema_context: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        normalized_question = question.strip()
        if not normalized_question:
            return None

        aggregate_result = self._build_semantic_aggregate_sql(
            normalized_question,
            intent_result,
            schema_context,
        )
        if aggregate_result:
            return aggregate_result

        if not self._is_text_lookup_question(normalized_question, intent_result):
            return None

        terms = self._extract_terms(normalized_question, schema_context)
        if not terms:
            return None

        for table_name in self._candidate_tables(normalized_question, intent_result, schema_context)[: self.max_tables]:
            table_schema = self._get_table_schema(table_name)
            text_columns = self._text_columns(table_schema)
            if not text_columns:
                continue

            selected_columns = self._selected_columns(table_schema, text_columns)
            threshold = self._match_threshold(terms)
            alias = self._alias_for(table_name)
            score_expression = self._score_expression(alias, text_columns, terms)
            where_expression = f"({score_expression}) >= {threshold}"
            sql = (
                f"SELECT {', '.join(f'{alias}.{column}' for column in selected_columns)}, "
                f"({score_expression}) AS match_score "
                f"FROM {table_name} {alias} "
                f"WHERE {where_expression} "
                f"ORDER BY match_score DESC, {self._stable_order(alias, table_schema)} "
                f"LIMIT {self.default_limit}"
            )
            return TextMatchSQLCandidate(
                sql=sql,
                table_name=table_name,
                terms=terms,
                text_columns=text_columns,
                selected_columns=selected_columns,
                threshold=threshold,
                reason="Generated deterministic text-match SQL for a lookup question over textual columns.",
            ).to_dict()

        return None

    def _build_semantic_aggregate_sql(
        self,
        question: str,
        intent_result: dict[str, Any],
        schema_context: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        operator = self._aggregate_operator(question, intent_result)
        if operator not in {"average", "sum"}:
            return None

        table_results = []
        ambiguous_results = []
        for table_name in self._candidate_tables(question, intent_result, schema_context)[: self.max_tables]:
            table_schema = self._get_table_schema(table_name)
            metric_result = self._resolve_metric_column(question, table_schema)
            if metric_result["status"] == "ambiguous":
                ambiguous_results.append((table_name, metric_result))
                continue
            if metric_result["status"] != "matched":
                continue

            table_results.append((table_name, table_schema, metric_result))

        if not table_results:
            if ambiguous_results:
                table_name, metric_result = ambiguous_results[0]
                options = ", ".join(metric_result["options"])
                return {
                    "status": "needs_clarification",
                    "sql": None,
                    "table_name": table_name,
                    "tables_used": [table_name],
                    "columns_used": [],
                    "assumptions": [],
                    "reason": f"无法确定要聚合哪个数值字段。可选字段：{options}",
                    "source": "semantic_aggregate",
                }
            return None

        table_name, table_schema, metric_result = sorted(
            table_results,
            key=lambda item: (-item[2]["score"], item[0]),
        )[0]
        metric_column = metric_result["column"]
        alias = self._alias_for(table_name)
        filter_terms = self._aggregate_filter_terms(question, table_schema, metric_column, operator)
        text_columns = self._text_columns(table_schema)
        where_clause = self._filter_where_clause(alias, text_columns, filter_terms)
        aggregate_expression = self._aggregate_expression(operator, alias, metric_column)
        aggregate_alias = self._aggregate_alias(operator, metric_column)
        sql = (
            f"SELECT {aggregate_expression} AS {aggregate_alias}, COUNT(*) AS matched_rows "
            f"FROM {table_name} {alias}"
        )
        if where_clause:
            sql = f"{sql} WHERE {where_clause}"

        return {
            "status": "success",
            "sql": sql,
            "table_name": table_name,
            "terms": filter_terms,
            "text_columns": text_columns,
            "selected_columns": [metric_column],
            "metric_column": metric_column,
            "columns_used": [
                f"{table_name}.{metric_column}",
                *[f"{table_name}.{column}" for column in text_columns if filter_terms],
            ],
            "threshold": 1,
            "reason": (
                "Generated deterministic semantic aggregate SQL after mapping the requested metric "
                f"to {table_name}.{metric_column}."
            ),
            "source": "semantic_aggregate",
        }

    def _is_text_lookup_question(self, question: str, intent_result: dict[str, Any]) -> bool:
        lowered = question.lower()
        if any(term in lowered for term in NON_TEXT_LOOKUP_TERMS):
            return False

        intent_type = str(intent_result.get("intent_type") or "")
        if intent_type not in {"simple_lookup", "join_query", "follow_up_query"}:
            return False

        if any(term in lowered for term in LOOKUP_TERMS):
            return True
        return bool((intent_result.get("entities") or {}).get("filters"))

    def _aggregate_operator(self, question: str, intent_result: dict[str, Any]) -> str | None:
        lowered = question.lower()
        metrics = {
            str(metric).lower()
            for metric in (intent_result.get("entities") or {}).get("metrics") or []
        }
        if any(term in lowered for term in AGGREGATE_AVERAGE_TERMS) or "average" in metrics:
            return "average"
        if any(term in lowered for term in AGGREGATE_SUM_TERMS) or "sum" in metrics:
            return "sum"
        return None

    def _resolve_metric_column(self, question: str, table_schema: dict[str, Any]) -> dict[str, Any]:
        metric_columns = self._metric_columns(table_schema)
        if not metric_columns:
            return {"status": "missing", "column": None, "score": 0, "options": []}

        scored = []
        for column in metric_columns:
            score, matches = self._semantic_column_score(question, column)
            scored.append(
                {
                    "column": str(column["name"]),
                    "score": score,
                    "matches": matches,
                }
            )

        scored.sort(key=lambda item: (-item["score"], item["column"]))
        best = scored[0]
        second_score = scored[1]["score"] if len(scored) > 1 else 0
        if best["score"] >= 12 and best["score"] - second_score >= 4:
            return {
                "status": "matched",
                "column": best["column"],
                "score": best["score"],
                "options": [item["column"] for item in scored[:3]],
                "matches": best["matches"],
            }

        if len(metric_columns) > 1:
            return {
                "status": "ambiguous",
                "column": None,
                "score": best["score"],
                "options": [item["column"] for item in scored[:5]],
                "matches": best["matches"],
            }

        return {"status": "missing", "column": None, "score": best["score"], "options": [best["column"]]}

    def _semantic_column_score(self, question: str, column: dict[str, Any]) -> tuple[int, list[str]]:
        question_terms = self._semantic_terms(question)
        column_text = self._column_semantic_text(column)
        column_terms = self._semantic_terms(column_text)
        metric_terms = question_terms - AGGREGATE_CONTROL_TERMS
        matches = sorted(metric_terms & column_terms)
        score = len(matches) * 10

        lowered_question = question.lower()
        lowered_column_text = column_text.lower()
        for alias, expansions in SEMANTIC_ALIASES.items():
            if alias in lowered_question and (expansions & column_terms):
                score += 6
                if alias not in matches:
                    matches.append(alias)

        column_name = str(column.get("name") or "").lower()
        if column_name and column_name in lowered_question:
            score += 20
        if self._is_identifier_column(column):
            score -= 8
        if any(term in column_name for term in ["count", "number", "amount", "total", "score", "rate"]):
            score += 2
        return max(score, 0), sorted(set(matches))

    def _metric_columns(self, table_schema: dict[str, Any]) -> list[dict[str, Any]]:
        numeric_columns = []
        primary_keys = set(table_schema.get("primary_keys") or [])
        for column in table_schema.get("columns", []):
            column_name = str(column.get("name") or "")
            column_type = str(column.get("type") or "").lower()
            if not column_name or not any(marker in column_type for marker in NUMERIC_TYPE_MARKERS):
                continue
            if column_name in primary_keys or self._is_identifier_column(column):
                continue
            numeric_columns.append(column)
        return numeric_columns

    def _is_identifier_column(self, column: dict[str, Any]) -> bool:
        column_name = str(column.get("name") or "").lower()
        return (
            column_name in IDENTIFIER_COLUMN_NAMES
            or column_name.endswith("_id")
            or column_name.startswith("id_")
        )

    def _column_semantic_text(self, column: dict[str, Any]) -> str:
        return " ".join(
            [
                str(column.get("name") or ""),
                str(column.get("description") or ""),
            ]
        )

    def _semantic_terms(self, text: str) -> set[str]:
        lowered = text.lower()
        terms = set(re.findall(r"[a-z0-9]+", lowered))
        for cjk_part in re.findall(r"[\u4e00-\u9fff]+", lowered):
            terms.add(cjk_part)
            if len(cjk_part) >= 2:
                terms.update(cjk_part[index : index + 2] for index in range(len(cjk_part) - 1))
        for alias, expansions in SEMANTIC_ALIASES.items():
            if alias in lowered:
                terms.add(alias)
                terms.update(expansions)
        for term in AGGREGATE_CONTROL_TERMS:
            if term in lowered:
                terms.add(term)
        return {term for term in terms if term}

    def _aggregate_filter_terms(
        self,
        question: str,
        table_schema: dict[str, Any],
        metric_column: str,
        operator: str,
    ) -> list[str]:
        residual = question.lower()
        residual = residual.replace(str(table_schema.get("name") or "").lower(), " ")
        residual = residual.replace(metric_column.lower(), " ")
        metric_column_schema = next(
            (column for column in table_schema.get("columns", []) if column.get("name") == metric_column),
            {},
        )
        metric_terms = self._semantic_terms(self._column_semantic_text(metric_column_schema))

        for token in metric_terms:
            if len(token) >= 2:
                residual = residual.replace(token.lower(), " ")
        for alias, expansions in SEMANTIC_ALIASES.items():
            if expansions & metric_terms:
                residual = residual.replace(alias, " ")
        for term in [
            *AGGREGATE_CONTROL_TERMS,
            *QUESTION_STOPWORDS,
            *QUERY_TYPE_TERMS,
            operator,
        ]:
            residual = residual.replace(str(term).lower(), " ")

        terms: list[str] = []
        for match in re.findall(r"[a-z0-9][a-z0-9_-]*", residual):
            if self._is_filter_term(match):
                terms.append(match)
        for match in re.findall(r"[\u4e00-\u9fff]{2,}", residual):
            cleaned = match.strip()
            if cleaned and cleaned not in QUERY_TYPE_TERMS and cleaned not in QUESTION_STOPWORDS:
                terms.append(cleaned)

        unique_terms = []
        for term in terms:
            if term not in unique_terms:
                unique_terms.append(term)
        return unique_terms[:5]

    def _is_filter_term(self, term: str) -> bool:
        if not term or term in AGGREGATE_CONTROL_TERMS or term in QUESTION_STOPWORDS:
            return False
        if term in QUERY_TYPE_TERMS:
            return False
        if len(term) < 2:
            return False
        return True

    def _filter_where_clause(self, alias: str, text_columns: list[str], filter_terms: list[str]) -> str:
        if not text_columns or not filter_terms:
            return ""

        term_clauses = []
        for term in filter_terms:
            pattern = self._like_pattern(term)
            column_checks = " OR ".join(
                f"CAST({alias}.{column} AS TEXT) ILIKE '{pattern}' ESCAPE '!'"
                for column in text_columns
            )
            term_clauses.append(f"({column_checks})")
        return " AND ".join(term_clauses)

    def _aggregate_expression(self, operator: str, alias: str, metric_column: str) -> str:
        if operator == "sum":
            return f"SUM({alias}.{metric_column})"
        return f"AVG({alias}.{metric_column})"

    def _aggregate_alias(self, operator: str, metric_column: str) -> str:
        prefix = "total" if operator == "sum" else "average"
        return f"{prefix}_{metric_column}"

    def _extract_terms(self, question: str, schema_context: list[dict[str, Any]]) -> list[str]:
        normalized = question.lower()
        for table_name in self._schema_table_names(schema_context):
            normalized = normalized.replace(table_name.lower(), " ")
        for stopword in sorted([*QUESTION_STOPWORDS, *QUERY_TYPE_TERMS], key=len, reverse=True):
            normalized = normalized.replace(stopword.lower(), " ")

        raw_terms: list[str] = []
        for part in re.split(r"[\s,，。；;:：?？!！、/\\|()\[\]（）【】<>《》]+", normalized):
            raw_terms.extend(self._split_term_part(part))

        terms = []
        for term in raw_terms:
            cleaned = term.strip().strip("_-")
            if self._is_usable_term(cleaned) and cleaned not in terms:
                terms.append(cleaned)
        return terms[:8]

    def _split_term_part(self, part: str) -> list[str]:
        if not part:
            return []
        if re.search(r"[\u4e00-\u9fff]", part):
            pieces = re.split(r"[和及与或]", part)
        else:
            pieces = re.split(r"\b(?:and|or)\b", part)
        split_terms: list[str] = []
        for piece in pieces:
            if not piece:
                continue
            split_terms.extend(self._split_cjk_compound(piece))
        return split_terms

    def _split_cjk_compound(self, value: str) -> list[str]:
        if not re.search(r"[\u4e00-\u9fff]", value):
            return [value]
        if len(value) <= 2:
            return [value]

        compact_value = re.sub(r"\s+", "", value)
        terms = [compact_value[index : index + 2] for index in range(0, len(compact_value) - 1, 2)]
        if len(compact_value) % 2 == 1 and len(compact_value) >= 3:
            terms.append(compact_value[-2:])
        return terms or [compact_value]

    def _is_usable_term(self, term: str) -> bool:
        if not term or term in QUESTION_STOPWORDS or term in QUERY_TYPE_TERMS:
            return False
        if term.isdigit():
            return False
        if re.fullmatch(r"[a-z_]{1}", term):
            return False
        if re.search(r"[\u4e00-\u9fff]", term):
            return len(term) >= 2
        return len(term) >= 3

    def _candidate_tables(
        self,
        question: str,
        intent_result: dict[str, Any],
        schema_context: list[dict[str, Any]],
    ) -> list[str]:
        candidates: list[str] = []
        for table_name in (intent_result.get("entities") or {}).get("tables") or []:
            if table_name and table_name not in candidates:
                candidates.append(str(table_name))
        for item in schema_context:
            table_name = item.get("table_name") or item.get("name")
            if table_name and table_name not in candidates:
                candidates.append(str(table_name))

        context_by_table = {
            str(item.get("table_name") or item.get("name")): item
            for item in schema_context
            if item.get("table_name") or item.get("name")
        }
        return sorted(
            candidates,
            key=lambda table_name: (
                -self._table_target_score(question, table_name, context_by_table.get(table_name, {})),
                candidates.index(table_name),
            ),
        )

    def _table_target_score(self, question: str, table_name: str, context_item: dict[str, Any]) -> int:
        score = 0
        lowered_question = question.lower()
        metadata_text = self._table_metadata_text(table_name, context_item).lower()
        source = str(context_item.get("source") or "")
        if "selected_scope" in source:
            score += 120
        if "value" in source:
            score += 90
        try:
            score += int(float(context_item.get("score") or 0) * 10)
        except (TypeError, ValueError):
            pass

        if table_name.lower() in lowered_question:
            score += 40
        for term in QUERY_TYPE_TERMS:
            lowered_term = term.lower()
            if lowered_term in lowered_question and lowered_term in metadata_text:
                score += 30
        return score

    def _table_metadata_text(self, table_name: str, context_item: dict[str, Any]) -> str:
        parts = [
            table_name,
            str(context_item.get("content") or ""),
            str(context_item.get("description") or ""),
        ]
        table_schema = self._get_table_schema(table_name)
        parts.append(str(table_schema.get("description") or ""))
        for column in table_schema.get("columns", []):
            parts.append(str(column.get("name") or ""))
            parts.append(str(column.get("description") or ""))
        return " ".join(parts)

    def _get_table_schema(self, table_name: str) -> dict[str, Any]:
        try:
            if hasattr(self.schema_service, "get_table_schema"):
                return self.schema_service.get_table_schema(table_name) or {}
            if hasattr(self.schema_service, "_get_table_schema"):
                return self.schema_service._get_table_schema(table_name) or {}
            return {}
        except Exception:
            return {}

    def _text_columns(self, table_schema: dict[str, Any]) -> list[str]:
        columns = []
        for column in table_schema.get("columns", []):
            column_name = str(column.get("name") or "")
            column_type = str(column.get("type") or "").lower()
            if column_name and any(marker in column_type for marker in TEXT_TYPE_MARKERS):
                columns.append(column_name)
        return columns

    def _selected_columns(self, table_schema: dict[str, Any], text_columns: list[str]) -> list[str]:
        available = [str(column.get("name")) for column in table_schema.get("columns", []) if column.get("name")]
        preferred = ["id", "name", "title", "description", "summary", *text_columns]
        selected = []
        for column in preferred:
            if column in available and column not in selected:
                selected.append(column)
        return selected[:6] or available[:6]

    def _match_threshold(self, terms: list[str]) -> int:
        if len(terms) <= 1:
            return 1
        if len(terms) <= 3:
            return 2
        return max(2, ceil(len(terms) * 0.6))

    def _score_expression(self, alias: str, text_columns: list[str], terms: list[str]) -> str:
        cases = []
        for term in terms:
            pattern = self._like_pattern(term)
            column_checks = " OR ".join(
                f"CAST({alias}.{column} AS TEXT) ILIKE '{pattern}' ESCAPE '!'"
                for column in text_columns
            )
            cases.append(f"(CASE WHEN {column_checks} THEN 1 ELSE 0 END)")
        return " + ".join(cases)

    def _like_pattern(self, term: str) -> str:
        escaped = term.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("'", "''")
        return f"%{escaped}%"

    def _stable_order(self, alias: str, table_schema: dict[str, Any]) -> str:
        primary_keys = table_schema.get("primary_keys") or []
        if primary_keys:
            return ", ".join(f"{alias}.{column} ASC" for column in primary_keys)
        for column in table_schema.get("columns", []):
            if column.get("name"):
                return f"{alias}.{column['name']} ASC"
        return "1 ASC"

    def _alias_for(self, table_name: str) -> str:
        parts = [part for part in table_name.split("_") if part]
        alias = "".join(part[0] for part in parts)[:3] or "t"
        if not alias[0].isalpha():
            alias = f"t{alias}"
        return alias

    def _schema_table_names(self, schema_context: list[dict[str, Any]]) -> list[str]:
        return [
            str(item.get("table_name") or item.get("name"))
            for item in schema_context
            if item.get("table_name") or item.get("name")
        ]
