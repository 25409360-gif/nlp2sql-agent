import unittest

from app.agent.result_summarizer import ResultSummarizer


class FakeResponse:
    def __init__(self, parsed_json=None, content="") -> None:
        self.parsed_json = parsed_json
        self.content = content


class ValidSummaryLLM:
    def chat_completion(self, **kwargs):
        return FakeResponse(
            parsed_json={
                "answer": "张三迟到次数最多，共 8 次。",
                "key_points": ["张三: 8 次"],
                "row_count": 999,
                "limitations": [],
                "follow_up_suggestions": ["可以查看具体迟到日期。"],
            }
        )

    def extract_json(self, content):
        raise AssertionError("extract_json should not be called")


class BadSummaryLLM:
    def chat_completion(self, **kwargs):
        return FakeResponse(parsed_json={"bad": "shape"}, content="not json")

    def extract_json(self, content):
        raise ValueError("bad json")


class ResultSummarizerTest(unittest.TestCase):
    def test_normal_result_summary(self) -> None:
        summarizer = ResultSummarizer(llm_client=ValidSummaryLLM())
        result = summarizer.summarize(
            question="谁迟到次数最多？",
            sql="SELECT name, late_count FROM ...",
            execution_result={
                "success": True,
                "columns": ["name", "late_count"],
                "rows": [{"name": "张三", "late_count": 8}],
                "row_count": 1,
                "execution_time_ms": 12.3,
            },
        )

        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["answer"], "张三迟到次数最多，共 8 次。")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["key_points"], ["张三: 8 次"])

    def test_empty_result_summary(self) -> None:
        summarizer = ResultSummarizer(llm_client=BadSummaryLLM())
        result = summarizer.summarize(
            question="上个月有哪些缺勤记录？",
            sql="SELECT name FROM users WHERE false",
            execution_result={
                "success": True,
                "columns": ["name"],
                "rows": [],
                "row_count": 0,
                "execution_time_ms": 2.0,
            },
        )

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["answer"], "没有找到符合条件的记录。")
        self.assertEqual(result["row_count"], 0)

    def test_fallback_summary_when_llm_fails(self) -> None:
        summarizer = ResultSummarizer(llm_client=BadSummaryLLM())
        result = summarizer.summarize(
            question="列出用户",
            sql="SELECT id, name FROM users LIMIT 2",
            execution_result={
                "success": True,
                "columns": ["id", "name"],
                "rows": [{"id": 1, "name": "王子轩"}, {"id": 2, "name": "李佳怡"}],
                "row_count": 2,
                "execution_time_ms": 2.0,
            },
        )

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["answer"], "查询返回 2 条记录。")
        self.assertEqual(len(result["key_points"]), 2)

    def test_execution_failure_summary(self) -> None:
        summarizer = ResultSummarizer(llm_client=ValidSummaryLLM())
        result = summarizer.summarize(
            question="列出用户",
            sql="SELECT missing_column FROM users",
            execution_result={
                "success": False,
                "error": "column missing_column does not exist",
            },
        )

        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["answer"], "查询执行失败，暂时无法总结结果。")
        self.assertIn("missing_column", result["limitations"][0])


if __name__ == "__main__":
    unittest.main()
