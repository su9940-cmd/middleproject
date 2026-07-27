"""maintenance_policy 순수 함수 테스트."""

import unittest

from app.agents.action_draft.maintenance_policy import (
    build_maintenance_request_draft,
    evaluate_maintenance_need,
)
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


class BuildMaintenanceRequestDraftTest(unittest.TestCase):
    def _draft(self, **overrides):
        kwargs = {
            "maintenance_request_id": "MR-AL-M0101-1",
            "alert_id": "AL-M0101-1",
            "machine_id": "M-0101",
            "machine_type": "REACTOR",
            "risk_level": RiskLevel.EMERGENCY,
            "maintenance_reason": "긴급 상태",
            "manual_id": "reactor_safety_manual",
        }
        kwargs.update(overrides)
        return build_maintenance_request_draft(**kwargs)

    def test_carries_identity_fields_through_unchanged(self) -> None:
        draft = self._draft()
        self.assertEqual(draft["maintenance_request_id"], "MR-AL-M0101-1")
        self.assertEqual(draft["alert_id"], "AL-M0101-1")
        self.assertEqual(draft["machine_id"], "M-0101")
        self.assertEqual(draft["machine_type"], "REACTOR")

    def test_title_and_recommendation_reference_the_reason_and_manual(self) -> None:
        draft = self._draft()
        self.assertIn("M-0101", draft["title"])
        self.assertIn("긴급 상태", draft["recommendation"])
        self.assertIn("reactor_safety_manual", draft["recommendation"])

    def test_missing_reason_falls_back_to_a_generic_phrase(self) -> None:
        draft = self._draft(maintenance_reason=None)
        self.assertIn("반복적인 위험 신호", draft["recommendation"])

    def test_missing_manual_id_omits_the_sop_reference(self) -> None:
        draft = self._draft(manual_id=None)
        self.assertNotIn("관련 SOP", draft["recommendation"])

    def test_priority_follows_risk_level(self) -> None:
        self.assertEqual(self._draft(risk_level=RiskLevel.EMERGENCY)["priority"], "높음")
        self.assertEqual(self._draft(risk_level=RiskLevel.WARNING)["priority"], "중간")
        self.assertEqual(self._draft(risk_level=RiskLevel.CAUTION)["priority"], "낮음")
        self.assertEqual(self._draft(risk_level=None)["priority"], "낮음")


if __name__ == "__main__":
    unittest.main()
