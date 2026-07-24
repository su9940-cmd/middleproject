"""ActionDraftAgent contract and integration tests."""

import json
import unittest

from app.agents.action_draft import ActionDraftAgent
from app.core.enums import ActionPhase, RiskLevel
from app.core.exceptions import ActionDraftError
from app.nodes.worker_interrupt import _build_interrupt_value


class FakeLLMClient:
    def __init__(self, response):
        self._response = response
        self.last_user_prompt = None

    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        self.last_user_prompt = user_prompt
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _doc(document_type="sop"):
    return {
        "source_id": "pump_safety_manual",
        "document_type": document_type,
        "title": "흡입 배관 확인",
        "section": "4.3",
        "content": "흡입 밸브 개도와 배관 막힘 여부를 확인한다.",
        "manual_version": "1.5",
    }


def _response():
    return json.dumps(
        {
            "summary": "펌프 저압 대응",
            "actions": [
                {
                    "title": "흡입 배관 확인",
                    "instruction": "흡입 밸브 개도와 배관 막힘 여부를 확인한다.",
                    "priority": "HIGH",
                    "required": True,
                    "source_keys": ["pump_safety_manual::4.3"],
                    "previously_failed": False,
                }
            ],
        },
        ensure_ascii=False,
    )


def _state(**overrides):
    state = {
        "alert_id": "AL-M0104-TEST",
        "machine_id": "M-0104",
        "machine_type": "PUMP",
        "risk_level": RiskLevel.WARNING,
        "sensor_reading": {"Pressure": 8.0, "Vibration": 4.8},
        "ml_risk_score": 0.72,
        "retrieved_documents": [_doc()],
        "memory_context": {},
        "manual_id": "pump_safety_manual",
        "machine_profile": {"manual_version": "1.5"},
    }
    state.update(overrides)
    return state


class ActionDraftAgentContractTest(unittest.TestCase):
    def test_returns_final_checklist_shaped_draft(self) -> None:
        draft = ActionDraftAgent(FakeLLMClient(_response()))(_state())["action_draft"]

        self.assertIn("checklist_id", draft)
        self.assertIn("items", draft)
        self.assertNotIn("actions", draft)
        self.assertEqual(draft["items"][0]["checklist_item_id"][:5], "ITEM-")
        self.assertEqual(draft["items"][0]["citations"][0]["section"], "4.3")

    def test_validator_can_pass_draft_unchanged_to_worker_interrupt(self) -> None:
        state = _state()
        draft = ActionDraftAgent(FakeLLMClient(_response()))(state)["action_draft"]
        state["final_checklist"] = draft

        _, checklist_id, _ = _build_interrupt_value(state)
        self.assertEqual(checklist_id, draft["checklist_id"])

    def test_initial_and_emergency_phase(self) -> None:
        initial = ActionDraftAgent(FakeLLMClient(_response()))(
            _state(risk_level=RiskLevel.CAUTION)
        )["action_draft"]
        emergency = ActionDraftAgent(FakeLLMClient(_response()))(
            _state(risk_level=RiskLevel.EMERGENCY, emergency_reasons=["Temp>=42"])
        )["action_draft"]

        self.assertEqual(initial["action_phase"], ActionPhase.INITIAL)
        self.assertEqual(emergency["action_phase"], ActionPhase.EMERGENCY)
        self.assertIn("Temp>=42", emergency["escalation_reason"])


class ActionDraftAgentRevisionTest(unittest.TestCase):
    def test_validator_feedback_and_previous_draft_are_in_revision_prompt(self) -> None:
        llm = FakeLLMClient(_response())
        previous = {"checklist_id": "CL-OLD", "items": [{"title": "이전 조치"}]}
        ActionDraftAgent(llm)(
            _state(
                validation_attempts=1,
                validation_feedback=[{"code": "UNSUPPORTED", "message": "근거 불충분"}],
                action_draft=previous,
            )
        )

        self.assertIn("근거 불충분", llm.last_user_prompt)
        self.assertIn("CL-OLD", llm.last_user_prompt)

    def test_revision_increments_checklist_version(self) -> None:
        draft = ActionDraftAgent(FakeLLMClient(_response()))(
            _state(validation_attempts=1)
        )["action_draft"]
        self.assertEqual(draft["version"], 2)
        self.assertTrue(draft["checklist_id"].endswith("-V2"))


class ActionDraftAgentFailureTest(unittest.TestCase):
    def test_missing_risk_or_documents_raises(self) -> None:
        agent = ActionDraftAgent(FakeLLMClient(_response()))
        with self.assertRaises(ActionDraftError):
            agent({"retrieved_documents": [_doc()]})
        with self.assertRaises(ActionDraftError):
            agent(_state(retrieved_documents=[]))

    def test_only_law_documents_cannot_become_fallback_actions(self) -> None:
        agent = ActionDraftAgent(FakeLLMClient(RuntimeError("down")))
        with self.assertRaises(ActionDraftError):
            agent(_state(retrieved_documents=[_doc(document_type="law")]))


class ActionDraftAgentMaintenanceTest(unittest.TestCase):
    def test_maintenance_policy_is_preserved(self) -> None:
        result = ActionDraftAgent(FakeLLMClient(_response()))(
            _state(
                risk_level=RiskLevel.EMERGENCY,
                memory_context={"is_repeat_limit_exceeded": True},
            )
        )
        self.assertTrue(result["requires_maintenance_request"])
        self.assertTrue(result["action_draft"]["requires_maintenance_request"])


if __name__ == "__main__":
    unittest.main()
