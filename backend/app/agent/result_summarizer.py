from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.prompts.result_summary_prompt import build_result_summary_prompt
from app.services.llm_client import LLMClient, LLMProviderError, create_llm_client


@dataclass
class ResultSummary:
    answer: str
    key_points: list[str] = field(default_factory=list)
    row_count: int = 0
    limitations: list[str] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)
    source: str = "llm"
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResultSummarizer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or create_llm_client()

    def summarize(
        self,
        question: str,
        sql: str,
        execution_result: dict[str, Any],
    ) -> dict[str, Any]:
        if not execution_result.get("success", False):
            return self._fallback_summary(question, execution_result, "Query execution failed").to_dict()

        rows = execution_result.get("rows") or []
        columns = execution_result.get("columns") or []
        row_count = int(execution_result.get("row_count") or len(rows))
        prompt = build_result_summary_prompt(
            question=question,
            sql=sql,
            columns=columns,
            rows=rows,
            row_count=row_count,
            execution_time_ms=execution_result.get("execution_time_ms"),
        )

        try:
            response = self._call_llm(prompt)
            parsed = response.parsed_json
            if parsed is None:
                parsed = self.llm_client.extract_json(response.content)
            return self._normalize_summary(parsed, row_count).to_dict()
        except Exception as exc:
            return self._fallback_summary(question, execution_result, str(exc)).to_dict()

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

    def _normalize_summary(self, raw: Any, actual_row_count: int) -> ResultSummary:
        if not isinstance(raw, dict):
            raise ValueError("summary response must be a JSON object")

        answer = str(raw.get("answer") or "").strip()
        if not answer:
            raise ValueError("summary response must include answer")

        return ResultSummary(
            answer=answer,
            key_points=self._string_list(raw.get("key_points")),
            row_count=actual_row_count,
            limitations=self._string_list(raw.get("limitations")),
            follow_up_suggestions=self._string_list(raw.get("follow_up_suggestions")),
            source="llm",
            raw_response=raw,
        )

    def _fallback_summary(
        self,
        question: str,
        execution_result: dict[str, Any],
        reason: str,
    ) -> ResultSummary:
        if not execution_result.get("success", False):
            return ResultSummary(
                answer="查询执行失败，暂时无法总结结果。",
                key_points=[],
                row_count=0,
                limitations=[execution_result.get("error") or reason],
                follow_up_suggestions=[],
                source="fallback",
            )

        rows = execution_result.get("rows") or []
        row_count = int(execution_result.get("row_count") or len(rows))
        if row_count == 0:
            return ResultSummary(
                answer="没有找到符合条件的记录。",
                key_points=[],
                row_count=0,
                limitations=["结果为空只能说明当前数据库中没有匹配记录。"],
                follow_up_suggestions=["可以尝试放宽筛选条件或调整时间范围。"],
                source="fallback",
            )

        key_points = [self._format_row(row) for row in rows[:3]]
        return ResultSummary(
            answer=f"查询返回 {row_count} 条记录。",
            key_points=key_points,
            row_count=row_count,
            limitations=[f"LLM 总结失败，已使用本地 fallback。原因：{reason}"],
            follow_up_suggestions=[],
            source="fallback",
        )

    def _format_row(self, row: dict[str, Any]) -> str:
        return ", ".join(f"{key}: {value}" for key, value in row.items())

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]
