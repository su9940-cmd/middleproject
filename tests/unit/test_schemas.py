"""Action Draft structured-output schema tests."""

import unittest

from pydantic import ValidationError

from app.agents.action_draft.schemas import DraftedAction, DraftedChecklist


def _valid_action(**overrides):
    value = {
        "title": "냉각수 확인",
        "instruction": "밸브 A-3 상태를 확인한다.",
        "priority": "HIGH",
        "required": True,
        "source_keys": ["SOP-R-014::4.3"],
        "previously_failed": False,
    }
    value.update(overrides)
    return value


class DraftedActionTest(unittest.TestCase):
    def test_valid_action_passes(self) -> None:
        action = DraftedAction(**_valid_action())
        self.assertEqual(action.source_keys, ["SOP-R-014::4.3"])

    def test_empty_or_blank_source_keys_are_rejected(self) -> None:
        for source_keys in ([], ["", "  "]):
            with self.subTest(source_keys=source_keys), self.assertRaises(ValidationError):
                DraftedAction(**_valid_action(source_keys=source_keys))

    def test_invalid_priority_and_extra_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action(priority="URGENT"))
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action(action_id="LLM-MINTED-ID"))

    def test_previously_failed_is_required_for_strict_schema(self) -> None:
        value = _valid_action()
        value.pop("previously_failed")
        with self.assertRaises(ValidationError):
            DraftedAction(**value)


class DraftedChecklistTest(unittest.TestCase):
    def test_checklist_accepts_structured_actions(self) -> None:
        checklist = DraftedChecklist(
            summary="온도 초과 대응",
            actions=[DraftedAction(**_valid_action())],
        )
        self.assertEqual(len(checklist.actions), 1)


if __name__ == "__main__":
    unittest.main()
