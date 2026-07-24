"""expression_filter 순수 함수 테스트."""

import unittest

from app.agents.validator.expression_filter import (
    contains_forbidden_expression,
    is_action_appropriate_for_risk,
    sanitize_action,
    sanitize_expression,
)
from app.core.enums import RiskLevel


class SanitizeExpressionTest(unittest.TestCase):
    def test_sanitize_replaces_law_violation_expression(self) -> None:
        result = sanitize_expression("법 위반 필요 사항입니다")
        self.assertNotIn("법 위반 필요", result)
        self.assertIn("검토 필요", result)

    def test_sanitize_preserves_safe_text(self) -> None:
        text = "냉각수 밸브를 확인하십시오"
        self.assertEqual(sanitize_expression(text), text)


class ContainsForbiddenExpressionTest(unittest.TestCase):
    def test_detects_various_patterns(self) -> None:
        self.assertTrue(contains_forbidden_expression("이는 법 위반 필요 사항"))
        self.assertTrue(contains_forbidden_expression("위법 필요한 경우"))
        self.assertFalse(contains_forbidden_expression("적용 검토 필요"))


class SanitizeActionTest(unittest.TestCase):
    def test_cleans_title_and_description(self) -> None:
        action = {"title": "법 위반 필요", "description": "위법 필요한 조치"}
        cleaned = sanitize_action(action)
        self.assertTrue("필요" not in cleaned["title"] or "검토" in cleaned["title"])
        self.assertTrue("필요" not in cleaned["description"] or "검토" in cleaned["description"])


class IsActionAppropriateForRiskTest(unittest.TestCase):
    def test_required_action_bypasses_risk_check(self) -> None:
        action = {"priority": "LOW", "required": True}
        self.assertTrue(is_action_appropriate_for_risk(action, RiskLevel.EMERGENCY))

    def test_low_priority_dropped_at_warning(self) -> None:
        action = {"priority": "LOW", "required": False}
        self.assertFalse(is_action_appropriate_for_risk(action, RiskLevel.WARNING))

    def test_medium_priority_passes_at_warning(self) -> None:
        action = {"priority": "MEDIUM", "required": False}
        self.assertTrue(is_action_appropriate_for_risk(action, RiskLevel.WARNING))

    def test_low_priority_passes_at_caution(self) -> None:
        action = {"priority": "LOW", "required": False}
        self.assertTrue(is_action_appropriate_for_risk(action, RiskLevel.CAUTION))


if __name__ == "__main__":
    unittest.main()
