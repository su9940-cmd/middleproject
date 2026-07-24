"""MemoryAgent 클래스 통합 테스트.

리포지토리는 프로토콜을 구조적으로 만족하는 페이크로 주입한다.
C의 실제 DB 구현이 없어도 이 테스트로 Memory Agent를 검증할 수 있다.
"""

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.memory import REPEAT_LIMIT_THRESHOLD, MemoryAgent
from app.core.enums import AlertStatus, RiskLevel
from app.core.exceptions import MemoryLookupError


# ---------------------------------------------------------------------------
# 페이크 리포지토리 (Protocol을 구조적으로 만족)
# ---------------------------------------------------------------------------

class FakeAlertRepository:
    def __init__(self, alerts: list[dict[str, Any]] | None = None) -> None:
        self._alerts = alerts or []

    def list_by_machine(
        self,
        machine_id: str,
        limit: int = 10,
        exclude_alert_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            alert
            for alert in self._alerts
            if alert["machine_id"] == machine_id
            and (
                exclude_alert_id is None
                or alert.get("alert_id") != exclude_alert_id
            )
        ][:limit]


class FakeChecklistRepository:
    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self._items = items or []

    def list_items_by_machine(
        self, machine_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        return [i for i in self._items if i["machine_id"] == machine_id][:limit]


class FakeWorkerResponseRepository:
    def __init__(self, note: str | None = None) -> None:
        self._note = note

    def latest_note_by_machine(self, machine_id: str) -> str | None:
        return self._note


class FakeMaintenanceRepository:
    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self._records = records or []

    def list_by_machine(
        self, machine_id: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        return list(self._records)


class ExplodingAlertRepository:
    """실패 처리 테스트용. 어떤 종류의 예외든 MemoryLookupError로 래핑되는지 확인."""

    def list_by_machine(
        self,
        machine_id: str,
        limit: int = 10,
        exclude_alert_id: str | None = None,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("DB 연결 실패")


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

MACHINE = "M-0101"
NOW = datetime(2026, 7, 23, 10, 15, tzinfo=timezone.utc)


def _make_agent(
    *,
    alerts: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    note: str | None = None,
    maintenance: list[dict[str, Any]] | None = None,
    alert_repo: Any = None,
) -> MemoryAgent:
    return MemoryAgent(
        alert_repository=alert_repo or FakeAlertRepository(alerts),
        checklist_repository=FakeChecklistRepository(items),
        worker_response_repository=FakeWorkerResponseRepository(note),
        maintenance_repository=FakeMaintenanceRepository(maintenance),
    )


# ---------------------------------------------------------------------------
# 정상 흐름
# ---------------------------------------------------------------------------

class MemoryAgentHappyPathTest(unittest.TestCase):
    def test_call_returns_only_memory_context_key(self) -> None:
        """RAG와 병렬 실행되므로 반환 키는 memory_context 하나만이어야 한다."""
        agent = _make_agent()
        result = agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})
        self.assertEqual(set(result.keys()), {"memory_context"})

    def test_empty_history_returns_all_contract_fields(self) -> None:
        agent = _make_agent()
        ctx = agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})["memory_context"]

        expected_keys = {
            "previous_alert_count",
            "unresolved_count",
            "previous_risk_level",
            "previous_checklist_items",
            "completed_action_ids",
            "failed_action_ids",
            "latest_worker_note",
            "maintenance_history",
            "repeat_count",
            "is_risk_escalated",
            "is_repeat_limit_exceeded",
        }
        self.assertEqual(set(ctx.keys()), expected_keys)

    def test_filters_out_other_machines(self) -> None:
        alerts = [
            {"machine_id": MACHINE, "alert_status": AlertStatus.OPEN, "risk_level": "CAUTION"},
            {"machine_id": "M-0102", "alert_status": AlertStatus.OPEN, "risk_level": "EMERGENCY"},
        ]
        agent = _make_agent(alerts=alerts)
        ctx = agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})["memory_context"]
        self.assertEqual(ctx["previous_alert_count"], 1)

    def test_current_alert_is_excluded_from_history(self) -> None:
        alerts = [
            {
                "machine_id": MACHINE,
                "alert_id": "CURRENT",
                "alert_status": AlertStatus.OPEN,
                "risk_level": RiskLevel.EMERGENCY,
            },
            {
                "machine_id": MACHINE,
                "alert_id": "PREVIOUS",
                "alert_status": AlertStatus.RESOLVED,
                "risk_level": RiskLevel.CAUTION,
            },
        ]
        agent = _make_agent(alerts=alerts)
        ctx = agent(
            {
                "machine_id": MACHINE,
                "alert_id": "CURRENT",
                "risk_level": RiskLevel.EMERGENCY,
            }
        )["memory_context"]

        self.assertEqual(ctx["previous_alert_count"], 1)
        self.assertEqual(ctx["previous_risk_level"], RiskLevel.CAUTION)
        self.assertTrue(ctx["is_risk_escalated"])

    def test_maintenance_history_is_forwarded_intact(self) -> None:
        maintenance = [
            {
                "maintenance_request_id": "MR-1",
                "requested_at": NOW - timedelta(days=1),
                "approval_status": "APPROVED",
                "priority": "HIGH",
            }
        ]
        agent = _make_agent(note="냉각수 부족 의심", maintenance=maintenance)
        ctx = agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})["memory_context"]

        self.assertEqual(ctx["latest_worker_note"], "냉각수 부족 의심")
        self.assertEqual(ctx["maintenance_history"], maintenance)


# ---------------------------------------------------------------------------
# 반복 초과
# ---------------------------------------------------------------------------

class MemoryAgentRepeatLimitTest(unittest.TestCase):
    def test_repeat_limit_triggered_by_state(self) -> None:
        agent = _make_agent()
        ctx = agent(
            {"machine_id": MACHINE, "risk_level": RiskLevel.WARNING, "repeat_count": REPEAT_LIMIT_THRESHOLD}
        )["memory_context"]
        self.assertEqual(ctx["repeat_count"], REPEAT_LIMIT_THRESHOLD)
        self.assertTrue(ctx["is_repeat_limit_exceeded"])

    def test_repeat_limit_triggered_by_unresolved_count(self) -> None:
        """State에 repeat_count가 없어도 미해결 경보 수가 임계값 이상이면 초과 판정."""
        alerts = [
            {"machine_id": MACHINE, "alert_status": AlertStatus.OPEN, "risk_level": "WARNING"},
            {"machine_id": MACHINE, "alert_status": AlertStatus.OPEN, "risk_level": "CAUTION"},
            {"machine_id": MACHINE, "alert_status": AlertStatus.IN_PROGRESS, "risk_level": "CAUTION"},
        ]
        agent = _make_agent(alerts=alerts)
        ctx = agent({"machine_id": MACHINE, "risk_level": RiskLevel.WARNING})["memory_context"]
        self.assertTrue(ctx["is_repeat_limit_exceeded"])


# ---------------------------------------------------------------------------
# 오류 처리 (raise 계약)
# ---------------------------------------------------------------------------

class MemoryAgentErrorHandlingTest(unittest.TestCase):
    def test_missing_machine_id_raises_memory_lookup_error(self) -> None:
        agent = _make_agent()
        with self.assertRaises(MemoryLookupError) as ctx:
            agent({"risk_level": RiskLevel.CAUTION})

        self.assertEqual(ctx.exception.error_code, "MEMORY_LOOKUP_FAILED")
        self.assertEqual(ctx.exception.details["failed_node"], "memory_agent")

    def test_repository_exception_is_wrapped_as_memory_lookup_error(self) -> None:
        agent = _make_agent(alert_repo=ExplodingAlertRepository())
        with self.assertRaises(MemoryLookupError) as ctx:
            agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})

        self.assertEqual(ctx.exception.error_code, "MEMORY_LOOKUP_FAILED")
        self.assertEqual(ctx.exception.details["failed_node"], "memory_agent")
        self.assertEqual(ctx.exception.details["machine_id"], MACHINE)
        # 원본 예외가 __cause__로 보존되어야 함
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)

    def test_agent_does_not_return_error_dict_on_failure(self) -> None:
        """실패 시 dict를 절대 반환하지 않는다 (계약: raise만)."""
        agent = _make_agent(alert_repo=ExplodingAlertRepository())
        try:
            result = agent({"machine_id": MACHINE, "risk_level": RiskLevel.CAUTION})
        except MemoryLookupError:
            return  # 정상: 예외로 실패를 알림
        self.fail(f"예외를 raise해야 하는데 dict를 반환함: {result}")


if __name__ == "__main__":
    unittest.main()
