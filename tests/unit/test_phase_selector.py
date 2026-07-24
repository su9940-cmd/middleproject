"""phase_selector 순수 함수 테스트."""

import unittest

from app.agents.action_draft.phase_selector import select_action_phase
from app.core.enums import ActionPhase, RiskLevel


class SelectActionPhaseTest(unittest.TestCase):
    def test_emergency_beats_all_other_signals(self) -> None:
        ctx = {"is_repeat_limit_exceeded": True, "is_risk_escalated": True, "unresolved_count": 5}
        self.assertEqual(select_action_phase(RiskLevel.EMERGENCY, ctx), ActionPhase.EMERGENCY)

    def test_initial_when_no_recurrence(self) -> None:
        ctx = {"is_repeat_limit_exceeded": False, "is_risk_escalated": False, "unresolved_count": 0}
        self.assertEqual(select_action_phase(RiskLevel.CAUTION, ctx), ActionPhase.INITIAL)

    def test_boolean_recurrence_signal_triggers_follow_up(self) -> None:
        for key in ["is_repeat_limit_exceeded", "is_risk_escalated"]:
            with self.subTest(key=key):
                self.assertEqual(select_action_phase(RiskLevel.CAUTION, {key: True}), ActionPhase.FOLLOW_UP)

    def test_unresolved_count_triggers_follow_up(self) -> None:
        self.assertEqual(select_action_phase(RiskLevel.CAUTION, {"unresolved_count": 1}), ActionPhase.FOLLOW_UP)

    def test_none_memory_defaults_to_initial(self) -> None:
        self.assertEqual(select_action_phase(RiskLevel.CAUTION, None), ActionPhase.INITIAL)


if __name__ == "__main__":
    unittest.main()
