"""Recovery Node — advances the alert lifecycle once a reading is NORMAL.

Only reached via `route_by_risk`'s "normal" branch (see `app.graph.routes`).
"""

from __future__ import annotations

from typing import Any

from app.core.enums import AlertStatus, MeasurementMode
from app.graph.state import SafetyState

_OPEN_ALERT_STATUSES = {
    AlertStatus.OPEN,
    AlertStatus.IN_PROGRESS,
    AlertStatus.WAITING_RECHECK,
    AlertStatus.MONITORING,
    AlertStatus.ESCALATED,
}


def recovery_node(state: SafetyState) -> dict[str, Any]:
    """Resolve/silence/monitor an alert after a NORMAL reading.

    Rules (contract section 8):
    - periodic + no open alert -> stay silent, no alert created.
    - immediate-recheck normal -> `MONITORING`, `consecutive_normal_count` = 1.
    - periodic normal while already `MONITORING` -> `RESOLVED`,
      `consecutive_normal_count` += 1 (two consecutive normals close the loop).
    - periodic normal while an alert is open but not yet `MONITORING`
      (worker hasn't submitted/rechecked yet): a single periodic normal
      doesn't skip the recheck-confirmation step, so `alert_status` is left
      unchanged and the count stays at 0.
    """

    measurement_mode = state["measurement_mode"]
    prior_status = state.get("alert_status") or AlertStatus.NONE
    prior_count = state.get("consecutive_normal_count") or 0

    if measurement_mode == MeasurementMode.IMMEDIATE_RECHECK:
        return {"alert_status": AlertStatus.MONITORING, "consecutive_normal_count": 1}

    if prior_status == AlertStatus.MONITORING:
        return {
            "alert_status": AlertStatus.RESOLVED,
            "consecutive_normal_count": prior_count + 1,
        }

    if prior_status not in _OPEN_ALERT_STATUSES:
        return {"alert_status": AlertStatus.NONE, "consecutive_normal_count": 0}

    return {"alert_status": prior_status, "consecutive_normal_count": 0}
