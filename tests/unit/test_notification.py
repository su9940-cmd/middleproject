"""Unit tests for `app.nodes.notification.send_immediate_alert`.

`app.nodes.notification` does `from app.services.notification_service import
send_alert`, binding the name locally - so these tests patch
`app.nodes.notification.send_alert` (not `app.services.notification_service.send_alert`,
which wouldn't affect the already-bound reference).
"""

from __future__ import annotations

from datetime import datetime

from app.core.enums import MachineType, NotificationStatus, RiskLevel
from app.core.exceptions import NotificationError
from app.nodes.notification import send_immediate_alert


def _state(**overrides) -> dict:
    state = {
        "alert_id": "AL-M0101-20260723T101500",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "risk_level": RiskLevel.EMERGENCY,
        "emergency_reasons": ["REACTOR: temperature 50.0 >= 42"],
    }
    state.update(overrides)
    return state


def test_send_immediate_alert_reports_sent_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.nodes.notification.send_alert",
        lambda alert_id, machine_id, message: None,
    )

    result = send_immediate_alert(_state())

    assert result["notification_status"] == NotificationStatus.SENT
    assert isinstance(result["immediate_alert_sent_at"], datetime)
    assert result["notification_error"] is None


def test_send_immediate_alert_reports_failed_instead_of_raising_on_notification_error(monkeypatch):
    """A delivery failure must never propagate - it would trip the shared
    error-code short-circuit and silently skip action_draft_node/validator_agent."""

    def _raise(alert_id: str, machine_id: str, message: str) -> None:
        raise NotificationError("Slack 알림 발송 실패: connection refused")

    monkeypatch.setattr("app.nodes.notification.send_alert", _raise)

    result = send_immediate_alert(_state())

    assert result == {
        "notification_status": NotificationStatus.FAILED,
        "notification_error": "Slack 알림 발송 실패: connection refused",
    }


def test_send_immediate_alert_reports_failed_on_unexpected_exception(monkeypatch):
    """Safety net: even a non-NotificationError failure must be reported, not raised."""

    def _raise(alert_id: str, machine_id: str, message: str) -> None:
        raise RuntimeError("paging service unreachable")

    monkeypatch.setattr("app.nodes.notification.send_alert", _raise)

    result = send_immediate_alert(_state())

    assert result == {
        "notification_status": NotificationStatus.FAILED,
        "notification_error": "paging service unreachable",
    }


def test_send_immediate_alert_without_webhook_configured_is_reported_as_failed(monkeypatch):
    """End-to-end through the real notification_service: no SLACK_ALERT_WEBHOOK_URL -> FAILED."""

    monkeypatch.delenv("SLACK_ALERT_WEBHOOK_URL", raising=False)

    result = send_immediate_alert(_state())

    assert result["notification_status"] == NotificationStatus.FAILED
    assert "SLACK_ALERT_WEBHOOK_URL" in result["notification_error"]
