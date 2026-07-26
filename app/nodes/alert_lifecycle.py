"""Alert Lifecycle - decides `alert_status`/`repeat_count` for abnormal/emergency readings.

`recovery_node` only runs on the NORMAL route (see `app.graph.routes.route_by_risk`)
and owns the alert-closing half of the 6-state lifecycle. Nothing in the
original 10-node design owned the other half - deciding what happens to
`alert_status` the moment a reading comes back CAUTION/WARNING/EMERGENCY -
so this node fills that gap. It's not one of the fixed node names in the
shared contract (section 7); if that's ever formalized, propose folding this
into an existing node rather than silently renaming it.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import AlertStatus
from app.graph.state import SafetyState

_MID_RECOVERY_STATUSES = {AlertStatus.WAITING_RECHECK, AlertStatus.MONITORING}


def alert_lifecycle_node(state: SafetyState) -> dict[str, Any]:
    """Open, reopen, or escalate the current alert based on this reading's risk level.

    Rules (matches the 6-state lifecycle: OPEN -> IN_PROGRESS -> WAITING_RECHECK
    -> MONITORING -> RESOLVED, with ESCALATED requiring a manager to clear it):
    - No alert yet (NONE/RESOLVED) -> open a new one: OPEN, or straight to
      ESCALATED if this reading is itself an emergency. repeat_count resets to 0.
    - Emergency, regardless of prior status -> ESCALATED (never auto-clears;
      only a manager resolving it should move it off ESCALATED).
    - Abnormal while mid recheck-confirmation (WAITING_RECHECK/MONITORING)
      -> back to OPEN (the confirmation attempt failed).
    - Abnormal while already OPEN/IN_PROGRESS/ESCALATED -> left as-is; it's
      already correctly flagged, just count the recurrence.
    - Any abnormal reading resets `consecutive_normal_count` to 0.

    Doesn't yet consider `memory_context` (previous_risk_level/is_risk_escalated/
    is_repeat_limit_exceeded) for a "worsening" or "repeat-limit" escalation
    trigger - `memory_agent` doesn't exist yet. Once it does, extend the
    emergency check below to also escalate on those signals.
    """

    prior_status = state.get("alert_status") or AlertStatus.NONE
    prior_repeat_count = state.get("repeat_count") or 0
    is_emergency = bool(state.get("emergency_reasons"))

    if prior_status in (AlertStatus.NONE, AlertStatus.RESOLVED):
        new_status = AlertStatus.ESCALATED if is_emergency else AlertStatus.OPEN
        repeat_count = 0
    else:
        repeat_count = prior_repeat_count + 1
        if is_emergency:
            new_status = AlertStatus.ESCALATED
        elif prior_status in _MID_RECOVERY_STATUSES:
            new_status = AlertStatus.OPEN
        else:
            new_status = prior_status

    return {
        "alert_status": new_status,
        "repeat_count": repeat_count,
        "consecutive_normal_count": 0,
    }
