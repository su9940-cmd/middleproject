"""ValidatorAgent 클래스 통합 테스트."""

import json
import unittest

from app.agents.validator import ValidatorAgent
from app.core.enums import RiskLevel
from app.core.exceptions import ChecklistValidationError


class FakeLLMClient:
    def __init__(self, response):
        self._response = response

    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _doc(source_id="SOP-1", title="냉각수", content="..."):
    return {"source_id": source_id, "document_type": "SOP", "title": title, "content": content}


def _action(action_id="SOP-1", title="냉각수 확인", priority="HIGH", required=True, source_ids=None):
    return {
        "action_id": action_id,
        "title": title,
        "description": "밸브 A-3 확인",
        "priority": priority,
        "required": required,
        "source_ids": source_ids or ["SOP-1"],
        "previously_failed": False,
    }


def _draft(actions=None, summary="요약"):
    return {"action_phase": "INITIAL", "summary": summary, "actions": actions or [_action()]}


def _review(verdict="SAFE"):
    return json.dumps({"overall_verdict": verdict, "concerns": [], "notes": ""})


class ValidatorAgentContractTest(unittest.TestCase):
    def test_returns_only_final_checklist_key(self) -> None:
        agent = ValidatorAgent()  # LLM 없어도 동작 가능
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
        })
        self.assertEqual(set(result.keys()), {"final_checklist"})

    def test_final_checklist_has_expected_fields(self) -> None:
        agent = ValidatorAgent()
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
        })
        fc = result["final_checklist"]
        self.assertIn("actions", fc)
        self.assertIn("final_status", fc)
        self.assertIn("safety_review", fc)  # LLM 없어도 safety_review는 항상 있음


class ValidatorAgentWithoutLLMTest(unittest.TestCase):
    """LLM 없이 규칙만 (기존 동작 유지)."""

    def test_safety_review_is_skipped(self) -> None:
        agent = ValidatorAgent()
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
        })
        self.assertEqual(result["final_checklist"]["safety_review"]["status"], "SKIPPED")

    def test_actions_still_filtered_by_grounding(self) -> None:
        agent = ValidatorAgent()
        # 하나는 유효, 하나는 환각
        actions = [_action("SOP-1", source_ids=["SOP-1"]), _action("FAKE", source_ids=["SOP-FAKE"])]
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(actions=actions),
            "retrieved_documents": [_doc(source_id="SOP-1")],
        })
        ids = {a["action_id"] for a in result["final_checklist"]["actions"]}
        self.assertEqual(ids, {"SOP-1"})


class ValidatorAgentWithLLMTest(unittest.TestCase):
    def test_safety_review_completed(self) -> None:
        llm = FakeLLMClient(_review(verdict="SAFE"))
        agent = ValidatorAgent(llm_client=llm)
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
            "machine_type": "REACTOR",
        })
        self.assertEqual(result["final_checklist"]["safety_review"]["status"], "COMPLETED")
        self.assertEqual(result["final_checklist"]["safety_review"]["overall_verdict"], "SAFE")

    def test_unsafe_verdict_does_not_remove_actions(self) -> None:
        """UNSAFE 판정이어도 조치는 그대로 통과, safety_review에 표시만."""
        llm = FakeLLMClient(_review(verdict="UNSAFE"))
        agent = ValidatorAgent(llm_client=llm)
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
        })
        fc = result["final_checklist"]
        self.assertEqual(len(fc["actions"]), 1)  # 조치는 그대로
        self.assertEqual(fc["safety_review"]["overall_verdict"], "UNSAFE")
        self.assertEqual(fc["final_status"], "READY_FOR_WORKER")  # 여전히 작업자에게 전달

    def test_llm_failure_does_not_break_validation(self) -> None:
        """LLM이 실패해도 규칙 기반 조치는 통과, safety_review에 FAILED 표시."""
        llm = FakeLLMClient(RuntimeError("LLM down"))
        agent = ValidatorAgent(llm_client=llm)
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(),
            "retrieved_documents": [_doc()],
        })
        fc = result["final_checklist"]
        self.assertEqual(len(fc["actions"]), 1)
        self.assertEqual(fc["safety_review"]["status"], "FAILED")
        self.assertEqual(fc["safety_review"]["overall_verdict"], "REVIEW_NEEDED")


class ValidatorAgentFallbackTest(unittest.TestCase):
    def test_all_actions_dropped_triggers_fallback(self) -> None:
        agent = ValidatorAgent()
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(actions=[_action("FAKE", source_ids=["SOP-FAKE"])]),
            "retrieved_documents": [_doc(source_id="SOP-1")],
        })
        fc = result["final_checklist"]
        self.assertEqual(fc["actions"], [])
        self.assertEqual(fc["final_status"], "READY_WITH_FALLBACK")
        self.assertEqual(fc["dropped_action_count"], 1)


class ValidatorAgentErrorHandlingTest(unittest.TestCase):
    def test_missing_risk_level_raises(self) -> None:
        agent = ValidatorAgent()
        with self.assertRaises(ChecklistValidationError):
            agent({"action_draft": _draft(), "retrieved_documents": []})

    def test_missing_action_draft_raises(self) -> None:
        agent = ValidatorAgent()
        with self.assertRaises(ChecklistValidationError):
            agent({"risk_level": RiskLevel.WARNING, "retrieved_documents": []})


class ValidatorAgentExpressionFilterTest(unittest.TestCase):
    def test_forbidden_expression_sanitized_before_llm_judgment(self) -> None:
        llm = FakeLLMClient(_review(verdict="SAFE"))
        agent = ValidatorAgent(llm_client=llm)
        action = _action(title="법 위반 필요 사항", source_ids=["SOP-1"])
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "action_draft": _draft(actions=[action]),
            "retrieved_documents": [_doc()],
        })
        title = result["final_checklist"]["actions"][0]["title"]
        self.assertNotIn("법 위반 필요", title)


if __name__ == "__main__":
    unittest.main()
