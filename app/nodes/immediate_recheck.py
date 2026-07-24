"""Immediate Recheck - asks for a confirmatory reading right after the worker responds.

Contract section 8. The actual new reading arrives later through the normal
`POST /sensors/ingest` entry point with `measurement_mode=IMMEDIATE_RECHECK`
(see `app.api.sensor_routes`) - this node only marks that a recheck is
pending; `app.graph.builder` wires it straight to `END` for this run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.enums import AlertStatus
from app.graph.state import SafetyState


def request_immediate_recheck(state: SafetyState) -> dict[str, Any]:
    """Mark the current alert as waiting on an immediate recheck reading."""

    return {
        "alert_status": AlertStatus.WAITING_RECHECK,
        "recheck_requested_at": datetime.now(timezone.utc),
    }
