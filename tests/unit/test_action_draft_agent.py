"""ActionDraftAgent 클래스 통합 테스트."""

import json
import unittest

from app.agents.action_draft import ActionDraftAgent
from app.core.enums import ActionPhase, RiskLevel
from app.core.exceptions import ActionDraftError


class FakeLLMClient:
    def __init__(self, response):
        self._response = response

    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _doc(source_id="SOP-R-014", document_type="SOP", title="냉각수", content="..."):
    return {"source_id": source_id, "document_type": document_type, "title": title, "content": content}


def _llm_response(actions=None, summary="LLM 요약"):
    return json.dumps({
        "summary": summary,
        "actions": actions or [{
            "action_id": "SOP-R-014",
            "title": "냉각수 확인",
            "description": "밸브 A-3 확인",
            "priority": "HIGH",
            "required": True,
            "source_ids": ["SOP-R-014"],
            "previously_failed": False,
        }],
    })


class ActionDraftAgentContractTest(unittest.TestCase):
    def test_returns_action_draft_and_maintenance_flag_only(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        result = agent({
            "risk_level": RiskLevel.CAUTION,
            "retrieved_documents": [_doc()],
            "memory_context": {},
        })
        self.assertEqual(set(result.keys()), {"action_draft", "requires_maintenance_request"})

    def test_draft_has_full_contract_schema(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        draft = agent({
            "risk_level": RiskLevel.CAUTION,
            "retrieved_documents": [_doc()],
            "memory_context": {},
        })["action_draft"]

        self.assertGreaterEqual(
            set(draft.keys()),
            {"action_phase", "summary", "actions", "maintenance_reason", "escalation_reason", "used_llm_fallback"},
        )


class ActionDraftAgentPhaseTest(unittest.TestCase):
    def test_initial_phase_when_first_incident(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        draft = agent({
            "risk_level": RiskLevel.CAUTION,
            "retrieved_documents": [_doc()],
            "memory_context": {},
        })["action_draft"]
        self.assertEqual(draft["action_phase"], ActionPhase.INITIAL)

    def test_emergency_phase_uses_emergency_reasons(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        draft = agent({
            "risk_level": RiskLevel.EMERGENCY,
            "emergency_reasons": ["Temp>=42"],
            "retrieved_documents": [_doc()],
            "memory_context": {},
        })["action_draft"]
        self.assertEqual(draft["action_phase"], ActionPhase.EMERGENCY)
        self.assertIn("Temp>=42", draft["escalation_reason"])


class ActionDraftAgentFallbackTest(unittest.TestCase):
    def test_llm_fallback_reflected_in_flag_and_summary(self) -> None:
        """LLM 실패 시 fallback 플래그가 True, summary에 표시됨."""
        agent = ActionDraftAgent(llm_client=FakeLLMClient(RuntimeError("LLM down")))
        result = agent({
            "risk_level": RiskLevel.WARNING,
            "retrieved_documents": [_doc()],
            "memory_context": {},
        })
        self.assertTrue(result["action_draft"]["used_llm_fallback"])
        self.assertIn("fallback", result["action_draft"]["summary"])
        # Fallback도 실제 조치를 만들어야 함
        self.assertGreaterEqual(len(result["action_draft"]["actions"]), 1)

    def test_no_documents_and_llm_fails_returns_empty_actions_gracefully(self) -> None:
        """RAG 결과가 비고 LLM도 실패해도 예외가 아니라 빈 조치로 처리."""
        agent = ActionDraftAgent(llm_client=FakeLLMClient(RuntimeError("down")))
        draft = agent({"risk_level": RiskLevel.CAUTION, "memory_context": {}})["action_draft"]
        self.assertEqual(draft["actions"], [])
        self.assertTrue(draft["used_llm_fallback"])


class ActionDraftAgentMaintenanceTest(unittest.TestCase):
    def test_maintenance_flag_reflects_policy(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        result = agent({
            "risk_level": RiskLevel.EMERGENCY,
            "retrieved_documents": [_doc()],
            "memory_context": {"is_repeat_limit_exceeded": True},
        })
        self.assertTrue(result["requires_maintenance_request"])
        self.assertIn("반복", result["action_draft"]["maintenance_reason"])

    def test_maintenance_blocked_when_active_request_exists(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        result = agent({
            "risk_level": RiskLevel.EMERGENCY,
            "retrieved_documents": [_doc()],
            "memory_context": {
                "is_repeat_limit_exceeded": True,
                "maintenance_history": [{"approval_status": "IN_PROGRESS"}],
            },
        })
        self.assertFalse(result["requires_maintenance_request"])
        self.assertIsNone(result["action_draft"]["maintenance_reason"])


class ActionDraftAgentErrorHandlingTest(unittest.TestCase):
    def test_missing_risk_level_raises(self) -> None:
        agent = ActionDraftAgent(llm_client=FakeLLMClient(_llm_response()))
        with self.assertRaises(ActionDraftError) as ctx:
            agent({"retrieved_documents": []})
        self.assertEqual(ctx.exception.error_code, "ACTION_DRAFT_FAILED")
        self.assertEqual(ctx.exception.details["failed_node"], "action_draft")


if __name__ == "__main__":
    unittest.main()
