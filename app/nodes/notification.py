"""Immediate Alert - dispatches the EMERGENCY notification (contract section 8).

Runs in parallel with `rag_agent`/`memory_agent` off of `alert_lifecycle_node`
(see `app.graph.builder._dispatch_from_alert_lifecycle`). A delivery failure
must never block the checklist path (contract section 8: "알림 실패가
RAG·Memory·체크리스트 생성 경로를 중단시키면 안 됩니다"), so failures are
caught here and reported through `notification_status`/`notification_error`
instead of raising - raising would trip `app.graph.builder._with_error_handling`
and cause `action_draft_node`/`validator_agent` to be skipped for a reason
unrelated to their own inputs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.enums import NotificationStatus
from app.graph.state import SafetyState
from app.services import notification_service

logger = logging.getLogger(__name__)


def send_immediate_alert(state: SafetyState) -> dict[str, Any]:
    """Send the EMERGENCY notification for the current alert.

    Reads `alert_id`, `machine_id`, `machine_type`, `risk_level`,
    `emergency_reasons` from `state`. Always returns normally - a delivery
    failure is reported via `notification_status=FAILED`, never raised.
    """

    payload = {
        "alert_id": state.get("alert_id"),
        "machine_id": state.get("machine_id"),
        "machine_type": state.get("machine_type"),
        "risk_level": state.get("risk_level"),
        "emergency_reasons": state.get("emergency_reasons", []),
    }

    try:
        notification_service.send_alert(payload)
    except Exception as exc:  # noqa: BLE001 - reported via state, never re-raised
        logger.error("immediate alert failed for %s: %s", payload.get("alert_id"), exc)
        return {
            "notification_status": NotificationStatus.FAILED,
            "notification_error": str(exc),
        }

    return {
        "notification_status": NotificationStatus.SENT,
        "immediate_alert_sent_at": datetime.now(timezone.utc),
        "notification_error": None,
    }
