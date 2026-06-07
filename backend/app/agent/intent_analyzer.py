from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.prompts.intent_analysis_prompt import INTENT_TYPES, build_intent_analysis_prompt
from app.services.llm_client import LLMClient, LLMProviderError, create_llm_client


INTENT_TYPE_SET = set(INTENT_TYPES)


TABLE_HINTS: dict[str, list[str]] = {
    "attendance_records": ["考勤", "打卡", "出勤", "迟到", "缺勤", "加班", "attendance"],
    "users": ["用户", "员工", "成员", "人员", "姓名", "user", "employee"],
    "departments": ["部门", "组织", "团队", "department"],
    "projects": ["项目", "课题", "project"],
    "project_members": ["项目成员", "参与项目", "项目角色"],
    "tasks": ["任务", "进度", "完成", "未完成", "截止", "工时", "task"],
    "devices": ["设备", "仪器", "服务器", "工作站", "device"],
    "device_usage_records": ["设备使用", "使用时长", "设备频率", "usage"],
    "meetings": ["会议", "纪要", "开会", "meeting"],
    "meeting_participants": ["参会", "参会人员", "会议参与"],
}


TABLE_ALIASES: dict[str, str] = {
    "attendance": "attendance_records",
    "attendance_record": "attendance_records",
    "employee": "users",
    "employees": "users",
    "user": "users",
    "department": "departments",
    "project": "projects",
    "project_member": "project_members",
    "project_membership": "project_members",
    "task": "tasks",
    "device": "devices",
    "equipment": "devices",
    "device_usage": "device_usage_records",
    "device_usages": "device_usage_records",
    "equipment_usage": "device_usage_records",
    "equipment_usages": "device_usage_records",
    "meeting": "meetings",
    "meeting_participant": "meeting_participants",
}

AGGREGATE_TERMS = {"平均", "均值", "总和", "合计", "数量", "总数", "次数", "多少", "avg", "average", "mean", "sum", "count"}
COMPARISON_TERMS = {
    "低于",
    "小于",
    "少于",
    "不超过",
    "以下",
    "高于",
    "大于",
    "超过",
    "多于",
    "以上",
    "below",
    "under",
    "less than",
    "above",
    "over",
    "greater than",
}
DIMENSION_REQUEST_TERMS = {"哪些", "哪个", "哪一个", "谁", "地方", "地点", "地区", "城市", "省份", "国家", "where", "which", "who"}
METRIC_SUBJECT_TERMS = {
    "气温",
    "温度",
    "摄氏",
    "华氏",
    "载客量",
    "乘客",
    "旅客",
    "客量",
    "收入",
    "营收",
    "金额",
    "价格",
    "费用",
    "成本",
    "时长",
    "工时",
    "小时",
    "分钟",
    "延误",
    "迟到",
    "数量",
    "次数",
}


@dataclass
class IntentAnalysisResult:
    intent_type: str
    confidence: float
    is_follow_up: bool
    requires_clarification: bool
    clarification_question: str | None
    entities: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    source: str = "llm"
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentAnalyzer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()

    def analyze(
        self,
        question: str,
        conversation_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        prompt = build_intent_analysis_prompt(
            question=normalized_question,
            conversation_context=conversation_context or [],
        )

        try:
            response = self._call_llm(prompt)
            parsed = response.parsed_json
            if parsed is None:
                parsed = self.llm_client.extract_json(response.content)
            return self._normalize_llm_result(parsed, normalized_question).to_dict()
        except Exception as exc:
            return self._fallback_result(
                question=normalized_question,
                conversation_context=conversation_context or [],
                reason=f"Fallback intent analysis used because LLM parsing failed: {exc}",
            ).to_dict()

    def _call_llm(self, prompt: dict[str, str]):
        try:
            return self.llm_client.chat_completion(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                json_mode=True,
                temperature=0.0,
            )
        except LLMProviderError:
            return self.llm_client.chat_completion(
                prompt=prompt["user"],
                system_prompt=prompt["system"],
                json_mode=False,
                temperature=0.0,
            )

    def _normalize_llm_result(self, raw: Any, question: str) -> IntentAnalysisResult:
        if not isinstance(raw, dict):
            raise ValueError("intent response must be a JSON object")

        intent_type = raw.get("intent_type")
        if intent_type not in INTENT_TYPE_SET:
            raise ValueError(f"unsupported intent_type: {intent_type}")

        question_lower = question.lower()
        entities = self._normalize_entities(raw.get("entities"), question_lower)
        inferred_intent_type = self._infer_intent_type(question_lower, [], entities["tables"])
        if self._is_destructive_question(question_lower):
            intent_type = "unsupported"
        else:
            intent_type = self._merge_intent_type(intent_type, inferred_intent_type, entities)

        requires_clarification = bool(raw.get("requires_clarification", False))
        if requires_clarification and self._can_continue_without_intent_clarification(
            question_lower,
            intent_type,
            entities,
        ):
            requires_clarification = False

        if intent_type == "simple_lookup" and len(entities["tables"]) >= 2:
            intent_type = "join_query"
        confidence = self._clamp_confidence(raw.get("confidence", 0.0))
        return IntentAnalysisResult(
            intent_type=intent_type,
            confidence=confidence,
            is_follow_up=bool(raw.get("is_follow_up", False)),
            requires_clarification=requires_clarification,
            clarification_question=(
                self._optional_string(raw.get("clarification_question")) if requires_clarification else None
            ),
            entities=entities,
            reason=str(raw.get("reason") or "LLM returned a valid intent classification."),
            source="llm",
            raw_response=raw,
        )

    def _merge_intent_type(
        self,
        llm_intent_type: str,
        inferred_intent_type: str,
        entities: dict[str, Any],
    ) -> str:
        if llm_intent_type == "simple_lookup" and inferred_intent_type in {
            "aggregate_query",
            "ranking_query",
            "time_series_query",
            "follow_up_query",
        }:
            return inferred_intent_type
        if llm_intent_type == "simple_lookup" and len(entities["tables"]) >= 2:
            return "join_query"
        return llm_intent_type

    def _can_continue_without_intent_clarification(
        self,
        question_lower: str,
        intent_type: str,
        entities: dict[str, Any],
    ) -> bool:
        if intent_type == "unsupported":
            return False

        if self._has_aggregate_comparison(question_lower) and self._has_dimension_request(question_lower):
            return True

        if "average" in entities.get("metrics", []) and self._has_metric_subject(question_lower):
            return True

        actionable_intents = {"aggregate_query", "ranking_query", "time_series_query", "join_query"}
        has_actionable_entity = any(
            [
                entities.get("tables"),
                entities.get("metrics"),
                entities.get("filters"),
                entities.get("time_range"),
                entities.get("sort"),
                entities.get("limit"),
            ]
        )
        return intent_type in actionable_intents and has_actionable_entity and self._has_query_shape(question_lower)

    def _has_aggregate_comparison(self, question_lower: str) -> bool:
        has_aggregate = any(term in question_lower for term in AGGREGATE_TERMS)
        has_comparison = any(term in question_lower for term in COMPARISON_TERMS)
        has_number = any(character.isdigit() for character in question_lower)
        return has_aggregate and has_comparison and has_number

    def _has_dimension_request(self, question_lower: str) -> bool:
        return any(term in question_lower for term in DIMENSION_REQUEST_TERMS)

    def _has_metric_subject(self, question_lower: str) -> bool:
        return any(term in question_lower for term in METRIC_SUBJECT_TERMS)

    def _has_query_shape(self, question_lower: str) -> bool:
        query_terms = {"哪些", "哪个", "谁", "多少", "列出", "查询", "查看", "show", "list", "which", "who", "what"}
        return any(term in question_lower for term in query_terms)

    def _fallback_result(
        self,
        question: str,
        conversation_context: list[dict[str, Any]],
        reason: str,
    ) -> IntentAnalysisResult:
        question_lower = question.lower()
        tables = self._infer_tables(question_lower)
        entities = {
            "tables": tables,
            "metrics": self._infer_metrics(question_lower),
            "filters": self._infer_filters(question_lower),
            "time_range": self._infer_time_range(question_lower),
            "sort": self._infer_sort(question_lower),
            "limit": self._infer_limit(question_lower),
        }

        intent_type = self._infer_intent_type(question_lower, conversation_context, tables)
        return IntentAnalysisResult(
            intent_type=intent_type,
            confidence=0.72 if intent_type != "unsupported" else 0.86,
            is_follow_up=intent_type == "follow_up_query",
            requires_clarification=False,
            clarification_question=None,
            entities=entities,
            reason=reason,
            source="fallback",
            raw_response=None,
        )

    def _infer_intent_type(
        self,
        question_lower: str,
        conversation_context: list[dict[str, Any]],
        tables: list[str],
    ) -> str:
        if self._is_destructive_question(question_lower):
            return "unsupported"

        if conversation_context and any(term in question_lower for term in ["那", "它", "他们", "继续", "再查", "这个"]):
            return "follow_up_query"

        if any(term in question_lower for term in ["趋势", "每天", "每日", "每周", "每月", "按天", "按月", "变化"]):
            return "time_series_query"

        if any(term in question_lower for term in ["最多", "最高", "最低", "最少", "排名", "top", "前"]):
            return "ranking_query"

        if any(term in question_lower for term in ["多少", "数量", "总数", "平均", "合计", "count", "sum", "avg"]):
            return "aggregate_query"

        if len(tables) >= 2:
            return "join_query"

        if not tables:
            return "unsupported"

        return "simple_lookup"

    def _is_destructive_question(self, question_lower: str) -> bool:
        destructive_terms = ["删除", "删掉", "清空", "drop", "delete", "update", "insert", "truncate", "alter"]
        return any(term in question_lower for term in destructive_terms)

    def _infer_tables(self, question_lower: str) -> list[str]:
        tables = []
        for table_name, terms in TABLE_HINTS.items():
            if table_name in question_lower or any(term.lower() in question_lower for term in terms):
                tables.append(table_name)
        return tables

    def _infer_metrics(self, question_lower: str) -> list[str]:
        metrics = []
        if any(term in question_lower for term in ["次数", "数量", "多少", "总数", "count"]):
            metrics.append("count")
        if any(term in question_lower for term in ["平均", "avg"]):
            metrics.append("average")
        if any(term in question_lower for term in ["合计", "总和", "sum"]):
            metrics.append("sum")
        if any(term in question_lower for term in ["时长", "工时", "小时", "分钟"]):
            metrics.append("duration")
        if any(term in question_lower for term in ["气温", "温度", "摄氏", "华氏"]):
            metrics.append("temperature")
        return metrics

    def _infer_filters(self, question_lower: str) -> list[str]:
        filters = []
        if "迟到" in question_lower:
            filters.append("status = late")
        if "缺勤" in question_lower:
            filters.append("status = absent")
        if "加班" in question_lower:
            filters.append("status = overtime")
        if "未完成" in question_lower or "没完成" in question_lower:
            filters.append("task status indicates incomplete")
        if "完成" in question_lower and "未完成" not in question_lower and "没完成" not in question_lower:
            filters.append("task status indicates completed")
        return filters

    def _infer_time_range(self, question_lower: str) -> str | None:
        for term in ["今天", "昨天", "本周", "上周", "本月", "上个月", "今年", "最近"]:
            if term in question_lower:
                return term
        return None

    def _infer_sort(self, question_lower: str) -> str | None:
        if any(term in question_lower for term in ["最多", "最高", "排名", "top", "前"]):
            return "desc"
        if any(term in question_lower for term in ["最少", "最低"]):
            return "asc"
        return None

    def _infer_limit(self, question_lower: str) -> int | None:
        if any(term in question_lower for term in ["最多", "最高", "最低", "最少"]):
            return 1
        return None

    def _normalize_entities(self, raw_entities: Any, question_lower: str) -> dict[str, Any]:
        raw = raw_entities if isinstance(raw_entities, dict) else {}
        table_names = self._normalize_table_names(raw.get("tables"))
        table_names = self._merge_unique(table_names, self._infer_tables(question_lower))
        raw_limit = self._optional_int(raw.get("limit"))
        return {
            "tables": table_names,
            "metrics": self._merge_unique(self._string_list(raw.get("metrics")), self._infer_metrics(question_lower)),
            "filters": self._merge_unique(self._string_list(raw.get("filters")), self._infer_filters(question_lower)),
            "time_range": self._optional_string(raw.get("time_range")) or self._infer_time_range(question_lower),
            "sort": self._optional_string(raw.get("sort")) or self._infer_sort(question_lower),
            "limit": raw_limit if raw_limit is not None else self._infer_limit(question_lower),
        }

    def _normalize_table_names(self, value: Any) -> list[str]:
        normalized_tables = []
        for table_name in self._string_list(value):
            normalized = table_name.strip().lower()
            normalized = TABLE_ALIASES.get(normalized, normalized)
            if normalized in TABLE_HINTS:
                normalized_tables.append(normalized)
        return self._merge_unique(normalized_tables, [])

    def _merge_unique(self, first: list[str], second: list[str]) -> list[str]:
        merged = []
        for item in [*first, *second]:
            if item not in merged:
                merged.append(item)
        return merged

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _clamp_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return max(0.0, min(1.0, confidence))
