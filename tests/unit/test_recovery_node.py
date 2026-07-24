"""Unit tests for `app.nodes.recovery.recovery_node`."""

from __future__ import annotations

from app.core.enums import AlertStatus, MeasurementMode
from app.nodes.recovery import recovery_node


def test_periodic_normal_with_no_open_alert_stays_silent():
    state = {
        "measurement_mode": MeasurementMode.PERIODIC,
        "alert_status": AlertStatus.NONE,
        "consecutive_normal_count": 0,
    }
    result = recovery_node(state)
    assert result == {"alert_status": AlertStatus.NONE, "consecutive_normal_count": 0}


def test_immediate_recheck_normal_moves_to_monitoring():
    state = {
        "measurement_mode": MeasurementMode.IMMEDIATE_RECHECK,
        "alert_status": AlertStatus.WAITING_RECHECK,
        "consecutive_normal_count": 0,
    }
    result = recovery_node(state)
    assert result == {"alert_status": AlertStatus.MONITORING, "consecutive_normal_count": 1}


def test_second_periodic_normal_while_monitoring_resolves():
    state = {
        "measurement_mode": MeasurementMode.PERIODIC,
        "alert_status": AlertStatus.MONITORING,
        "consecutive_normal_count": 1,
    }
    result = recovery_node(state)
    assert result == {"alert_status": AlertStatus.RESOLVED, "consecutive_normal_count": 2}


def test_periodic_normal_while_alert_open_but_not_yet_monitoring_is_left_unchanged():
    """A single periodic normal must not skip the recheck-confirmation step."""

    state = {
        "measurement_mode": MeasurementMode.PERIODIC,
        "alert_status": AlertStatus.OPEN,
        "consecutive_normal_count": 0,
    }
    result = recovery_node(state)
    assert result == {"alert_status": AlertStatus.OPEN, "consecutive_normal_count": 0}


def test_missing_alert_status_defaults_to_none():
    state = {"measurement_mode": MeasurementMode.PERIODIC}
    result = recovery_node(state)
    assert result == {"alert_status": AlertStatus.NONE, "consecutive_normal_count": 0}
