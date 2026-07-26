"""Persistence nodes — save pipeline state to the database.

Each node opens its own DB session via `app.core.db.session_scope` (nodes
run inside LangGraph, not an HTTP request, so there's no `Depends()` to
inject one) and returns only the fields it changed, per the shared node
contract. None of these three write back into `SafetyState` itself — the
database write is a side effect — so on success they all return `{}`.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.db import session_scope
from app.core.exceptions import DatabaseOperationError
from app.graph.state import SafetyState
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository
from app.repositories.sensor_repository import SensorRepository

logger = logging.getLogger(__name__)


async def save_sensor_reading(state: SafetyState) -> dict[str, Any]:
    """Persist the current `sensor_reading` to the database."""

    sensor_reading = state.get("sensor_reading")
    if not sensor_reading:
        logger.warning("save_sensor_reading called without sensor_reading in state")
        return {}

    try:
        async with session_scope() as session:
            await SensorRepository(session).save_sensor_reading(sensor_reading)
        logger.info("persisted sensor reading %s", state.get("reading_id"))
        return {}
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        raise DatabaseOperationError(
            f"failed to save sensor reading: {exc}",
            details={"reading_id": state.get("reading_id")},
        ) from exc


async def save_worker_response(state: SafetyState) -> dict[str, Any]:
    """Persist the worker's checklist response, if one was submitted."""

    worker_response = state.get("worker_response")
    if not worker_response:
        logger.debug("no worker_response present, skipping save_worker_response")
        return {}

    final_checklist = state.get("final_checklist") or {}
    checklist_id = final_checklist.get("checklist_id") or worker_response.get("checklist_id")
    if not checklist_id:
        logger.warning("save_worker_response called without a resolvable checklist_id")
        return {}

    try:
        async with session_scope() as session:
            await ChecklistRepository(session).update_worker_response(
                checklist_id, worker_response
            )
        logger.info("persisted worker response for checklist %s", checklist_id)
        return {}
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        raise DatabaseOperationError(
            f"failed to save worker response: {exc}",
            details={"checklist_id": checklist_id, "alert_id": state.get("alert_id")},
        ) from exc


async def save_alert_state(state: SafetyState) -> dict[str, Any]:
    """Persist or update the current alert lifecycle row."""

    alert_id = state.get("alert_id")
    if not alert_id:
        logger.debug("save_alert_state called without alert_id, skipping")
        return {}

    alert_data = {
        "alert_id": alert_id,
        "thread_id": state.get("thread_id"),
        "machine_id": state.get("machine_id"),
        "machine_type": state.get("machine_type"),
        "reading_id": state.get("reading_id"),
        "risk_level": state.get("risk_level"),
        "alert_status": state.get("alert_status"),
        "repeat_count": state.get("repeat_count", 0),
        "consecutive_normal_count": state.get("consecutive_normal_count", 0),
        "emergency_reasons": state.get("emergency_reasons", []),
        "notification_status": state.get("notification_status"),
        "requires_maintenance_request": state.get("requires_maintenance_request", False),
        "maintenance_request_id": state.get("maintenance_request_id"),
    }
    alert_payload = {key: value for key, value in alert_data.items() if value is not None}

    try:
        async with session_scope() as session:
            await AlertRepository(session).upsert_alert_state(alert_payload)
        logger.info("persisted alert state for %s", alert_id)
        return {}
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        raise DatabaseOperationError(
            f"failed to save alert state: {exc}",
            details={"alert_id": alert_id},
        ) from exc
