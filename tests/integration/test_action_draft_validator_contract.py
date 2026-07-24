"""End-to-end contract test for Action Draft, Validator and Worker Interrupt."""

import json
import unittest

from app.agents.action_draft import ActionDraftAgent
from app.agents.validator import ValidatorAgent
from app.core.enums import RiskLevel
from app.nodes.worker_interrupt import _build_interrupt_value


class FakeActionLLM:
    def generate_structured(self, **_: object) -> str:
        return json.dumps({
            "summary": "Pump checklist",
            "actions": [{
                "title": "Inspect inlet valve",
                "instruction": "Inspect the inlet valve opening and check for blockage.",
                "priority": "HIGH",
                "required": True,
                "source_keys": ["pump-manual::4.3"],
                "previously_failed": False,
            }],
        })


class ActionDraftValidatorContractTest(unittest.TestCase):
    def test_grounded_draft_reaches_worker_with_ids_intact(self) -> None:
        state = {
            "alert_id": "AL-1",
            "machine_id": "PUMP-1",
            "machine_type": "PUMP",
            "risk_level": RiskLevel.WARNING,
            "sensor_reading": {"pressure": 8.0},
            "retrieved_documents": [{
                "source_id": "pump-manual",
                "document_type": "sop",
                "section": "4.3",
                "title": "Inspect inlet valve",
                "content": "Inspect the inlet valve opening and check for blockage.",
            }],
            "memory_context": {},
        }
        draft_result = ActionDraftAgent(FakeActionLLM())(state)
        state.update(draft_result)
        validation_result = ValidatorAgent()(state)

        self.assertEqual(validation_result["validation_status"], "PASSED")
        self.assertEqual(
            validation_result["final_checklist"]["items"],
            draft_result["action_draft"]["items"],
        )
        state.update(validation_result)
        _, checklist_id, _ = _build_interrupt_value(state)
        self.assertEqual(checklist_id, draft_result["action_draft"]["checklist_id"])


if __name__ == "__main__":
    unittest.main()
