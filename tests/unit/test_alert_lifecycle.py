"""Unit tests for `app.nodes.alert_lifecycle.alert_lifecycle_node`."""

from __future__ import annotations

from app.core.enums import AlertStatus
from app.nodes.alert_lifecycle import alert_lifecycle_node


def _state(alert_status: AlertStatus | None, repeat_count: int = 0, emergency: bool = False) -> dict:
    return {
        "alert_status": alert_status,
        "repeat_count": repeat_count,
        "emergency_reasons": ["some rule tripped"] if emergency else [],
    }


def test_first_abnormal_reading_opens_a_new_alert():
    result = alert_lifecycle_node(_state(AlertStatus.NONE))
    assert result == {
        "alert_status": AlertStatus.OPEN,
        "repeat_count": 0,
        "consecutive_normal_count": 0,
    }


def test_first_emergency_reading_escalates_directly():
    result = alert_lifecycle_node(_state(AlertStatus.NONE, emergency=True))
    assert result["alert_status"] == AlertStatus.ESCALATED
    assert result["repeat_count"] == 0


def test_resolved_alert_reopens_like_a_fresh_one():
    result = alert_lifecycle_node(_state(AlertStatus.RESOLVED, repeat_count=5))
    assert result == {
        "alert_status": AlertStatus.OPEN,
        "repeat_count": 0,
        "consecutive_normal_count": 0,
    }


def test_still_open_and_still_abnormal_stays_open_and_counts_recurrence():
    result = alert_lifecycle_node(_state(AlertStatus.OPEN, repeat_count=2))
    assert result["alert_status"] == AlertStatus.OPEN
    assert result["repeat_count"] == 3


def test_in_progress_and_still_abnormal_is_left_as_is():
    result = alert_lifecycle_node(_state(AlertStatus.IN_PROGRESS, repeat_count=1))
    assert result["alert_status"] == AlertStatus.IN_PROGRESS
    assert result["repeat_count"] == 2


def test_failed_recheck_during_waiting_recheck_reopens():
    result = alert_lifecycle_node(_state(AlertStatus.WAITING_RECHECK, repeat_count=1))
    assert result["alert_status"] == AlertStatus.OPEN
    assert result["repeat_count"] == 2


def test_failed_recheck_during_monitoring_reopens():
    result = alert_lifecycle_node(_state(AlertStatus.MONITORING, repeat_count=1))
    assert result["alert_status"] == AlertStatus.OPEN


def test_emergency_always_escalates_even_when_already_open():
    result = alert_lifecycle_node(_state(AlertStatus.OPEN, repeat_count=1, emergency=True))
    assert result["alert_status"] == AlertStatus.ESCALATED


def test_escalated_does_not_auto_downgrade_without_a_manager_action():
    """A non-emergency reading on an already-ESCALATED alert must not quietly clear it."""

    result = alert_lifecycle_node(_state(AlertStatus.ESCALATED, repeat_count=3))
    assert result["alert_status"] == AlertStatus.ESCALATED
    assert result["repeat_count"] == 4


def test_abnormal_reading_always_resets_consecutive_normal_count():
    result = alert_lifecycle_node(_state(AlertStatus.OPEN, repeat_count=0))
    assert result["consecutive_normal_count"] == 0
