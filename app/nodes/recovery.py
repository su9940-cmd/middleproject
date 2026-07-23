"""Normal-reading recovery and consecutive-normal state transitions."""

from __future__ import annotations

from typing import Any

from app.core.enums import AlertStatus, MeasurementMode, RiskLevel
from app.core.exceptions import ApplicationError
from app.graph.state import SafetyState


class RecoveryStateError(ApplicationError):
    """Raised when the recovery node receives inconsistent graph state."""

    error_code = "RECOVERY_STATE_FAILED"


ACTIVE_ALERT_STATUSES = {
    AlertStatus.OPEN,
    AlertStatus.IN_PROGRESS,
    AlertStatus.WAITING_RECHECK,
    AlertStatus.MONITORING,
    AlertStatus.ESCALATED,
}


def recovery_node(state: SafetyState) -> dict[str, Any]:
    """Update recovery state for a NORMAL prediction without sending an alert."""

    try:
        risk_level = RiskLevel(state["risk_level"])
        if risk_level is not RiskLevel.NORMAL:
            raise RecoveryStateError("recovery_node only accepts NORMAL risk_level")

        measurement_mode = MeasurementMode(
            state.get("measurement_mode", MeasurementMode.PERIODIC)
        )
        alert_status = AlertStatus(state.get("alert_status", AlertStatus.NONE))
        normal_count = max(0, int(state.get("consecutive_normal_count", 0)))

        next_status, next_count = _next_recovery_state(
            alert_status=alert_status,
            measurement_mode=measurement_mode,
            normal_count=normal_count,
        )
    except Exception as exc:
        error = exc if isinstance(exc, RecoveryStateError) else RecoveryStateError(str(exc))
        return {
            "error_code": error.error_code,
            "error_message": str(error),
            "failed_node": "recovery_node",
        }

    return {
        "alert_status": next_status,
        "consecutive_normal_count": next_count,
        "error_code": None,
        "error_message": None,
        "failed_node": None,
    }


def _next_recovery_state(
    *,
    alert_status: AlertStatus,
    measurement_mode: MeasurementMode,
    normal_count: int,
) -> tuple[AlertStatus, int]:
    if alert_status is AlertStatus.NONE:
        return AlertStatus.NONE, 0
    if alert_status is AlertStatus.RESOLVED:
        return AlertStatus.RESOLVED, max(normal_count, 2)
    if alert_status not in ACTIVE_ALERT_STATUSES:
        raise RecoveryStateError(f"unsupported alert status: {alert_status}")

    if measurement_mode is MeasurementMode.IMMEDIATE_RECHECK:
        return AlertStatus.MONITORING, 1

    if alert_status is AlertStatus.MONITORING:
        next_count = normal_count + 1
        if next_count >= 2:
            return AlertStatus.RESOLVED, next_count
        return AlertStatus.MONITORING, next_count

    # A periodic normal reading for an active alert starts conservative monitoring.
    return AlertStatus.MONITORING, 1
