"""Unit tests for `app.nodes.notification.send_immediate_alert`."""

from __future__ import annotations

from datetime import datetime

from app.core.enums import MachineType, NotificationStatus, RiskLevel
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
    monkeypatch.setattr("app.services.notification_service.send_alert", lambda payload: None)

    result = send_immediate_alert(_state())

    assert result["notification_status"] == NotificationStatus.SENT
    assert isinstance(result["immediate_alert_sent_at"], datetime)
    assert result["notification_error"] is None


def test_send_immediate_alert_reports_failed_instead_of_raising(monkeypatch):
    """A delivery failure must never propagate - it would trip the shared
    error-code short-circuit and silently skip action_draft_node/validator_agent."""

    def _raise(payload: dict) -> None:
        raise RuntimeError("paging service unreachable")

    monkeypatch.setattr("app.services.notification_service.send_alert", _raise)

    result = send_immediate_alert(_state())

    assert result == {
        "notification_status": NotificationStatus.FAILED,
        "notification_error": "paging service unreachable",
    }


def test_send_immediate_alert_missing_alert_id_is_reported_as_failed(monkeypatch):
    result = send_immediate_alert(_state(alert_id=None))

    assert result["notification_status"] == NotificationStatus.FAILED
    assert result["notification_error"]
