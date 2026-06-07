import unittest

from app.agent.intent_analyzer import IntentAnalyzer
from app.services.llm_client import LLMResponse


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload

    def chat_completion(self, **kwargs):
        return LLMResponse(
            content="{}",
            model="fake",
            provider="fake",
            parsed_json=self.payload,
        )

    def extract_json(self, content):
        return self.payload


def intent_payload(**overrides):
    payload = {
        "intent_type": "simple_lookup",
        "confidence": 0.7,
        "is_follow_up": False,
        "requires_clarification": False,
        "clarification_question": None,
        "entities": {
            "tables": [],
            "metrics": [],
            "filters": [],
            "time_range": None,
            "sort": None,
            "limit": None,
        },
        "reason": "fake intent",
    }
    payload.update(overrides)
    return payload


class IntentAnalyzerTest(unittest.TestCase):
    def test_aggregate_comparison_does_not_stop_at_intent_clarification(self) -> None:
        analyzer = IntentAnalyzer(
            llm_client=FakeLLMClient(
                intent_payload(
                    requires_clarification=True,
                    clarification_question="请补充查询对象（如城市、省份等）和时间范围。",
                )
            )
        )

        result = analyzer.analyze("有哪些地方平均气温低于25摄氏度")

        self.assertEqual(result["intent_type"], "aggregate_query")
        self.assertFalse(result["requires_clarification"])
        self.assertIsNone(result["clarification_question"])
        self.assertIn("average", result["entities"]["metrics"])
        self.assertIn("temperature", result["entities"]["metrics"])

    def test_metric_subject_average_does_not_stop_at_intent_clarification(self) -> None:
        analyzer = IntentAnalyzer(
            llm_client=FakeLLMClient(
                intent_payload(
                    requires_clarification=True,
                    clarification_question="请补充时间范围。",
                )
            )
        )

        result = analyzer.analyze("B787的平均载客量多少")

        self.assertEqual(result["intent_type"], "aggregate_query")
        self.assertFalse(result["requires_clarification"])
        self.assertIsNone(result["clarification_question"])
        self.assertIn("average", result["entities"]["metrics"])

    def test_vague_question_keeps_llm_clarification(self) -> None:
        analyzer = IntentAnalyzer(
            llm_client=FakeLLMClient(
                intent_payload(
                    requires_clarification=True,
                    clarification_question="请补充要查询的对象。",
                )
            )
        )

        result = analyzer.analyze("帮我查一下")

        self.assertEqual(result["intent_type"], "simple_lookup")
        self.assertTrue(result["requires_clarification"])
        self.assertEqual(result["clarification_question"], "请补充要查询的对象。")

    def test_destructive_question_is_always_unsupported(self) -> None:
        analyzer = IntentAnalyzer(llm_client=FakeLLMClient(intent_payload()))

        result = analyzer.analyze("把用户删掉")

        self.assertEqual(result["intent_type"], "unsupported")
        self.assertFalse(result["requires_clarification"])


if __name__ == "__main__":
    unittest.main()
