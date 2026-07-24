"""Validator contract tests for the Action Draft -> Worker path."""

import json
import unittest

from app.agents.validator import ValidatorAgent
from app.core.enums import RiskLevel
from app.core.exceptions import ChecklistValidationError
from app.nodes.worker_interrupt import _build_interrupt_value


class FakeLLMClient:
    def __init__(self, response: str | Exception) -> None:
        self._response = response

    def generate_structured(self, **_: object) -> str:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _document() -> dict:
    return {
        "source_id": "pump-manual",
        "document_type": "sop",
        "section": "4.3",
        "title": "Inspect inlet valve",
        "content": "Inspect the inlet valve opening and check for blockage.",
    }


def _item(item_id: str = "ITEM-1", **overrides: object) -> dict:
    item = {
        "checklist_item_id": item_id,
        "action_id": "ACTION-1",
        "title": "Inspect inlet valve",
        "instruction": "Inspect the inlet valve opening and check for blockage.",
        "priority": "HIGH",
        "required": True,
        "citations": [
            {
                "source_key": "pump-manual::4.3",
                "source_id": "pump-manual",
                "document_type": "sop",
                "section": "4.3",
                "manual_version": None,
                "source_excerpt": "Inspect the inlet valve opening and check for blockage.",
            }
        ],
        "previously_failed": False,
    }
    item.update(overrides)
    return item


def _draft(items: list[dict] | None = None) -> dict:
    return {
        "checklist_id": "CL-AL-1-V1",
        "alert_id": "AL-1",
        "version": 1,
        "items": items or [_item()],
        "summary": "Pump warning checklist",
    }


def _state(**overrides: object) -> dict:
    state = {
        "risk_level": RiskLevel.WARNING,
        "machine_type": "PUMP",
        "action_draft": _draft(),
        "retrieved_documents": [_document()],
        "validation_attempts": 0,
    }
    state.update(overrides)
    return state


class ValidatorAgentContractTest(unittest.TestCase):
    def test_passed_draft_keeps_worker_contract(self) -> None:
        draft = _draft()
        result = ValidatorAgent()(_state(action_draft=draft))

        self.assertEqual(result["validation_status"], "PASSED")
        self.assertEqual(result["final_checklist"]["checklist_id"], draft["checklist_id"])
        self.assertEqual(result["final_checklist"]["items"], draft["items"])
        self.assertEqual(result["final_checklist"]["safety_review"]["status"], "SKIPPED")

        worker_state = {
            "alert_id": "AL-1",
            "machine_id": "PUMP-1",
            "final_checklist": result["final_checklist"],
        }
        self.assertEqual(_build_interrupt_value(worker_state)[1], "CL-AL-1-V1")

    def test_ungrounded_item_requests_revision(self) -> None:
        item = _item(citations=[{**_item()["citations"][0], "source_id": "unknown"}])
        result = ValidatorAgent()(_state(action_draft=_draft([item])))

        self.assertEqual(result["validation_status"], "REVISE")
        self.assertEqual(result["validation_attempts"], 1)
        self.assertEqual(result["validation_feedback"][0]["code"], "UNGROUNDED_CITATION")
        self.assertNotIn("final_checklist", result)

    def test_forbidden_legal_expression_requests_revision_without_rewriting(self) -> None:
        item = _item(instruction="법 위반 필요 여부를 확인한다.")
        result = ValidatorAgent()(_state(action_draft=_draft([item])))

        self.assertEqual(result["validation_status"], "REVISE")
        self.assertEqual(result["validation_feedback"][0]["code"], "FORBIDDEN_LEGAL_EXPRESSION")
        self.assertEqual(item["instruction"], "법 위반 필요 여부를 확인한다.")

    def test_duplicate_items_request_revision(self) -> None:
        result = ValidatorAgent()(_state(action_draft=_draft([_item(), _item("ITEM-2")])))
        self.assertEqual(result["validation_status"], "REVISE")
        codes = {entry["code"] for entry in result["validation_feedback"]}
        self.assertIn("DUPLICATE_ITEM", codes)

    def test_llm_review_is_advisory_after_deterministic_pass(self) -> None:
        llm = FakeLLMClient(json.dumps({
            "overall_verdict": "UNSAFE", "concerns": [], "notes": "manual review",
        }))
        result = ValidatorAgent(llm)(_state())
        self.assertEqual(result["validation_status"], "PASSED")
        self.assertEqual(result["final_checklist"]["safety_review"]["overall_verdict"], "UNSAFE")

    def test_missing_required_input_raises(self) -> None:
        with self.assertRaises(ChecklistValidationError):
            ValidatorAgent()({"risk_level": RiskLevel.WARNING})
        with self.assertRaises(ChecklistValidationError):
            ValidatorAgent()({"action_draft": _draft()})


if __name__ == "__main__":
    unittest.main()
