"""LLM 구조화 출력 스키마 테스트."""

import unittest

from pydantic import ValidationError

from app.agents.action_draft.schemas import DraftedAction, DraftedChecklist


def _valid_action_dict(**overrides):
    base = {
        "action_id": "SOP-R-014",
        "title": "냉각수 확인",
        "description": "밸브 A-3 확인",
        "priority": "HIGH",
        "required": True,
        "source_ids": ["SOP-R-014"],
    }
    base.update(overrides)
    return base


class DraftedActionTest(unittest.TestCase):
    def test_valid_action_passes(self) -> None:
        action = DraftedAction(**_valid_action_dict())
        self.assertEqual(action.action_id, "SOP-R-014")
        self.assertFalse(action.previously_failed)

    def test_empty_source_ids_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action_dict(source_ids=[]))

    def test_blank_source_ids_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action_dict(source_ids=["", "  "]))

    def test_invalid_priority_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action_dict(priority="URGENT"))

    def test_extra_fields_forbidden(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action_dict(malicious_field="hack"))

    def test_empty_title_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DraftedAction(**_valid_action_dict(title=""))


class DraftedChecklistTest(unittest.TestCase):
    def test_checklist_accepts_multiple_actions(self) -> None:
        checklist = DraftedChecklist(
            summary="온도 초과 대응",
            actions=[DraftedAction(**_valid_action_dict())],
        )
        self.assertEqual(len(checklist.actions), 1)

    def test_checklist_accepts_empty_actions_list(self) -> None:
        """빈 조치 목록은 스키마에 허용 - 안전장치 통과 후 fallback이 처리."""
        checklist = DraftedChecklist(summary="", actions=[])
        self.assertEqual(checklist.actions, [])


if __name__ == "__main__":
    unittest.main()
