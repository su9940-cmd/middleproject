"""safety_judge 테스트 - LLM 판정기 안전 원칙 검증."""

import json
import unittest

from app.agents.validator.safety_judge import judge_safety


class FakeLLMClient:
    def __init__(self, response):
        self._response = response

    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _action(action_id="A1", title="t", description="d", priority="HIGH"):
    return {
        "action_id": action_id,
        "title": title,
        "description": description,
        "priority": priority,
        "required": True,
        "previously_failed": False,
        "source_ids": ["SOP-1"],
    }


def _review(verdict="SAFE", concerns=None, notes=""):
    return json.dumps({
        "overall_verdict": verdict,
        "concerns": concerns or [],
        "notes": notes,
    })


class JudgeSafetyHappyPathTest(unittest.TestCase):
    def test_completed_review_returns_verdict_and_concerns(self) -> None:
        llm = FakeLLMClient(_review(verdict="REVIEW_NEEDED", concerns=[
            {"action_id": "A1", "severity": "WARNING", "reason": "우선순위 재검토"},
        ]))
        review = judge_safety(llm=llm, actions=[_action("A1")], risk_level="WARNING", machine_type="REACTOR")

        self.assertEqual(review["status"], "COMPLETED")
        self.assertEqual(review["overall_verdict"], "REVIEW_NEEDED")
        self.assertEqual(len(review["concerns"]), 1)


class JudgeSafetySafetyPrincipleTest(unittest.TestCase):
    """안전 원칙: LLM은 조치를 제거하지 않음."""

    def test_unsafe_verdict_does_not_return_actions_modification(self) -> None:
        """UNSAFE 판정이어도 safety_judge는 조치를 수정·제거하지 않음."""
        llm = FakeLLMClient(_review(verdict="UNSAFE"))
        review = judge_safety(llm=llm, actions=[_action()], risk_level="EMERGENCY", machine_type=None)

        # 반환에는 오직 판정 정보만 있고 actions 필드는 없음
        self.assertNotIn("actions", review)
        self.assertEqual(review["overall_verdict"], "UNSAFE")

    def test_hallucinated_action_id_in_concerns_dropped(self) -> None:
        """LLM이 존재하지 않는 action_id로 concern을 만들면 제거."""
        llm = FakeLLMClient(_review(concerns=[
            {"action_id": "A1", "severity": "INFO", "reason": "정상"},
            {"action_id": "HALLUCINATED", "severity": "CRITICAL", "reason": "존재하지 않는 조치"},
        ]))
        review = judge_safety(llm=llm, actions=[_action("A1")], risk_level="CAUTION", machine_type=None)
        ids = {c["action_id"] for c in review["concerns"]}
        self.assertEqual(ids, {"A1"})


class JudgeSafetyFailureHandlingTest(unittest.TestCase):
    def test_llm_none_returns_skipped(self) -> None:
        review = judge_safety(llm=None, actions=[_action()], risk_level="WARNING", machine_type=None)
        self.assertEqual(review["status"], "SKIPPED")
        self.assertEqual(review["overall_verdict"], "SAFE")  # 판정 없음은 통과로 간주

    def test_empty_actions_returns_skipped_without_llm_call(self) -> None:
        """조치가 없으면 LLM 호출조차 하지 않음 (판정할 것이 없으므로)."""
        llm = FakeLLMClient(RuntimeError("should not be called"))
        review = judge_safety(llm=llm, actions=[], risk_level="WARNING", machine_type=None)
        self.assertEqual(review["status"], "SKIPPED")

    def test_llm_exception_returns_failed_status(self) -> None:
        llm = FakeLLMClient(RuntimeError("LLM API down"))
        review = judge_safety(llm=llm, actions=[_action()], risk_level="WARNING", machine_type=None)
        self.assertEqual(review["status"], "FAILED")
        # 실패 시 REVIEW_NEEDED로 표시해 사람이 확인할 여지
        self.assertEqual(review["overall_verdict"], "REVIEW_NEEDED")

    def test_malformed_json_returns_failed_status(self) -> None:
        llm = FakeLLMClient("not json")
        review = judge_safety(llm=llm, actions=[_action()], risk_level="WARNING", machine_type=None)
        self.assertEqual(review["status"], "FAILED")

    def test_schema_violation_returns_failed_status(self) -> None:
        """LLM이 유효하지 않은 verdict 값을 반환하면 FAILED."""
        llm = FakeLLMClient(json.dumps({"overall_verdict": "INVALID", "concerns": [], "notes": ""}))
        review = judge_safety(llm=llm, actions=[_action()], risk_level="WARNING", machine_type=None)
        self.assertEqual(review["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
