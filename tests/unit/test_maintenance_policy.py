"""maintenance_policy 순수 함수 테스트."""

import unittest

from app.agents.action_draft.maintenance_policy import evaluate_maintenance_need
from app.core.enums import RiskLevel


class EvaluateMaintenanceNeedTest(unittest.TestCase):
    def test_no_signal_returns_no_maintenance(self) -> None:
        requires, reason = evaluate_maintenance_need(RiskLevel.CAUTION, {})
        self.assertFalse(requires)
        self.assertIsNone(reason)

    def test_repeat_limit_triggers(self) -> None:
        requires, reason = evaluate_maintenance_need(RiskLevel.CAUTION, {"is_repeat_limit_exceeded": True})
        self.assertTrue(requires)
        self.assertIn("반복 3회 이상", reason)

    def test_emergency_triggers(self) -> None:
        requires, reason = evaluate_maintenance_need(RiskLevel.EMERGENCY, {})
        self.assertTrue(requires)
        self.assertIn("긴급 상태", reason)

    def test_escalation_at_warning_triggers(self) -> None:
        ctx = {"is_risk_escalated": True, "previous_risk_level": "CAUTION"}
        requires, reason = evaluate_maintenance_need(RiskLevel.WARNING, ctx)
        self.assertTrue(requires)
        self.assertIn("경고 이상", reason)

    def test_escalation_below_warning_does_not_trigger(self) -> None:
        ctx = {"is_risk_escalated": True, "previous_risk_level": "NORMAL"}
        requires, reason = evaluate_maintenance_need(RiskLevel.CAUTION, ctx)
        self.assertFalse(requires)
        self.assertIsNone(reason)

    def test_active_maintenance_blocks_even_with_strong_signal(self) -> None:
        ctx = {"is_repeat_limit_exceeded": True, "maintenance_history": [{"approval_status": "APPROVED"}]}
        requires, reason = evaluate_maintenance_need(RiskLevel.EMERGENCY, ctx)
        self.assertFalse(requires)
        self.assertIsNone(reason)

    def test_completed_maintenance_does_not_block(self) -> None:
        ctx = {"is_repeat_limit_exceeded": True, "maintenance_history": [{"approval_status": "COMPLETED"}]}
        requires, _ = evaluate_maintenance_need(RiskLevel.CAUTION, ctx)
        self.assertTrue(requires)


if __name__ == "__main__":
    unittest.main()
