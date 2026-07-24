"""context_builder의 순수 함수 단위 테스트.

리포지토리·State가 필요 없는 로직만 검증한다.
"""

import unittest

from app.agents.memory.context_builder import (
    collect_previous_titles,
    compute_repeat_count,
    count_unresolved,
    extract_previous_risk_level,
    is_risk_escalated,
    partition_action_ids,
)
from app.core.enums import AlertStatus, RiskLevel


class CountUnresolvedTest(unittest.TestCase):
    def test_ignores_resolved_and_none(self) -> None:
        alerts = [
            {"alert_status": AlertStatus.OPEN},
            {"alert_status": AlertStatus.RESOLVED},
            {"alert_status": AlertStatus.MONITORING},
            {"alert_status": AlertStatus.NONE},
            {},  # 상태 필드 없음
        ]
        self.assertEqual(count_unresolved(alerts), 2)

    def test_on_empty_list(self) -> None:
        self.assertEqual(count_unresolved([]), 0)


class ExtractPreviousRiskLevelTest(unittest.TestCase):
    def test_returns_first_available(self) -> None:
        alerts = [
            {"risk_level": "WARNING"},
            {"risk_level": "CAUTION"},
        ]
        self.assertEqual(extract_previous_risk_level(alerts), "WARNING")

    def test_skips_empty_and_returns_next(self) -> None:
        alerts = [
            {},
            {"risk_level": None},
            {"risk_level": "CAUTION"},
        ]
        self.assertEqual(extract_previous_risk_level(alerts), "CAUTION")

    def test_none_when_absent(self) -> None:
        self.assertIsNone(extract_previous_risk_level([]))
        self.assertIsNone(extract_previous_risk_level([{"risk_level": None}]))


class IsRiskEscalatedTest(unittest.TestCase):
    def test_is_risk_escalated(self) -> None:
        cases = [
            ("CAUTION", RiskLevel.EMERGENCY, True),
            ("WARNING", RiskLevel.EMERGENCY, True),
            ("NORMAL", RiskLevel.CAUTION, True),
            ("WARNING", RiskLevel.CAUTION, False),
            ("EMERGENCY", RiskLevel.EMERGENCY, False),
            (None, RiskLevel.EMERGENCY, False),
            ("CAUTION", None, False),
            ("INVALID", RiskLevel.EMERGENCY, False),
        ]
        for previous, current, expected in cases:
            with self.subTest(previous=previous, current=current):
                self.assertIs(is_risk_escalated(previous, current), expected)


class PartitionActionIdsTest(unittest.TestCase):
    def test_splits_and_ignores_missing_ids(self) -> None:
        items = [
            {"action_id": "A1", "status": "COMPLETED"},
            {"action_id": "A2", "status": "FAILED"},
            {"action_id": "A3", "status": "PENDING"},
            {"action_id": None, "status": "COMPLETED"},  # 무시
            {"status": "COMPLETED"},  # 무시
        ]
        completed, failed = partition_action_ids(items)
        self.assertEqual(completed, ["A1"])
        self.assertEqual(failed, ["A2"])

    def test_preserves_input_order(self) -> None:
        items = [
            {"action_id": "A1", "status": "COMPLETED"},
            {"action_id": "A2", "status": "COMPLETED"},
            {"action_id": "A3", "status": "COMPLETED"},
        ]
        completed, _ = partition_action_ids(items)
        self.assertEqual(completed, ["A1", "A2", "A3"])


class CollectPreviousTitlesTest(unittest.TestCase):
    def test_skips_missing_titles(self) -> None:
        items = [
            {"title": "밸브 점검"},
            {"title": ""},
            {"title": None},
            {},
            {"title": "온도 확인"},
        ]
        self.assertEqual(collect_previous_titles(items), ["밸브 점검", "온도 확인"])


class ComputeRepeatCountTest(unittest.TestCase):
    def test_takes_max(self) -> None:
        self.assertEqual(compute_repeat_count(state_repeat_count=1, unresolved_count=3), 3)
        self.assertEqual(compute_repeat_count(state_repeat_count=5, unresolved_count=2), 5)
        self.assertEqual(compute_repeat_count(state_repeat_count=0, unresolved_count=0), 0)


if __name__ == "__main__":
    unittest.main()
