"""FastAPI routes for IoT sensor data ingestion.

There's no real IoT hardware yet, so this single endpoint stands in for it -
every reading (the first one on a machine or a later immediate-recheck one)
arrives here as a manually-submitted request, distinguished only by the
`measurement_mode` field in the body.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.action_draft.maintenance_policy import build_maintenance_request_draft
from app.core.db import get_db_session
from app.core.enums import AlertStatus, MeasurementMode
from app.core.ids import build_thread_id, generate_alert_id, generate_maintenance_request_id
from app.models.sensor import SensorReading
from app.nodes.persistence import save_alert_state, save_sensor_reading
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository
from app.repositories.maintenance_repository import MaintenanceRequestRepository
from app.repositories.sensor_repository import SensorRepository

router = APIRouter(prefix="/sensors", tags=["Sensors"])


@router.get("/latest/{machine_id}")
async def get_latest_sensor_reading(
    machine_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Return the last persisted reading so the dashboard survives refreshes."""

    reading = await SensorRepository(session).get_latest_by_machine(machine_id)
    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sensor reading found for machine {machine_id}",
        )
    return {
        "reading_id": reading.reading_id,
        "machine_id": reading.machine_id,
        "machine_type": reading.machine_type.value,
        "measured_at": reading.measured_at,
        "measurement_mode": reading.measurement_mode.value,
        "temperature": reading.temperature,
        "pressure": reading.pressure,
        "humidity": reading.humidity,
        "vibration": reading.vibration,
        "speed": reading.speed,
        "age": reading.age,
        "service_days": reading.service_days,
        "gas": reading.gas,
        "sparks": reading.sparks,
        "shift": reading.shift.value,
        "experience": reading.experience.value,
        "training": reading.training.value,
        "created_at": reading.created_at,
    }


def get_safety_graph(request: Request) -> CompiledStateGraph:
    """Fetch the graph compiled once at startup (see `main.py`'s `lifespan`)."""

    return request.app.state.safety_graph


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_sensor_data(
    reading: SensorReading,
    session: AsyncSession = Depends(get_db_session),
    graph: CompiledStateGraph = Depends(get_safety_graph),
) -> dict[str, Any]:
    """Persist a reading, resume the machine's open alert if any, run the safety graph.

    1. Save the raw reading (every reading is stored, not just abnormal ones).
    2. Look up whether this machine already has an active (non-RESOLVED)
       alert - if so, reuse its `alert_id`/`thread_id` so the graph resumes
       the same incident instead of starting a fresh one.
    3. Run the graph and persist whatever alert state it produced.
    """

    state: dict[str, Any] = {
        "reading_id": reading.reading_id,
        "machine_id": reading.machine_id,
        "machine_type": reading.machine_type,
        "measured_at": reading.measured_at,
        "measurement_mode": reading.measurement_mode,
        "sensor_reading": reading.model_dump(),
    }
    if reading.measurement_mode == MeasurementMode.IMMEDIATE_RECHECK:
        state["recheck_reading_id"] = reading.reading_id
    await save_sensor_reading(state)

    active_alert = await AlertRepository(session).get_active_alert_by_machine(reading.machine_id)
    if active_alert is not None:
        alert_id = active_alert.alert_id
        state["alert_status"] = active_alert.alert_status
        state["repeat_count"] = active_alert.repeat_count
        state["consecutive_normal_count"] = active_alert.consecutive_normal_count
    else:
        alert_id = generate_alert_id(reading.machine_id, reading.measured_at)
        state["alert_status"] = AlertStatus.NONE
        state["repeat_count"] = 0
        state["consecutive_normal_count"] = 0

    state["alert_id"] = alert_id
    thread_id = build_thread_id(reading.machine_id, alert_id)
    state["thread_id"] = thread_id

    result = await graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    if result.get("error_code"):
        # The reading itself is already safely persisted above; only the
        # risk assessment failed. Report that clearly instead of a false 201.
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "reading_id": reading.reading_id,
                "error_code": result.get("error_code"),
                "message": result.get("error_message"),
                "failed_node": result.get("failed_node"),
            },
        )

    # `action_draft_node` decides `requires_maintenance_request` (FR-14) but
    # never mints an id for it - do that here, before `save_alert_state`, so
    # the alert row and the draft row (created below) share the same
    # deterministic `MR-{alert_id}` id instead of the alert pointing at
    # nothing.
    if result.get("requires_maintenance_request") and result.get("alert_id"):
        result["maintenance_request_id"] = generate_maintenance_request_id(result["alert_id"])

    # Only persist an alert row once the graph has actually assigned a real
    # status - a plain NORMAL-with-no-open-alert reading stays silent (FR-05).
    if result.get("alert_status") not in (None, AlertStatus.NONE):
        await save_alert_state(result)

    # `"__interrupt__"` is set instead of the run reaching END whenever
    # `worker_interrupt` pauses it (see `app.nodes.worker_interrupt`) - by
    # then `validator_agent` has already produced `final_checklist`, so save
    # it now rather than waiting on a node that never runs again this request.
    is_awaiting_worker_response = "__interrupt__" in result
    final_checklist = result.get("final_checklist")
    if is_awaiting_worker_response and final_checklist:
        await ChecklistRepository(session).save_checklist(final_checklist)

        # `create_draft` is idempotent per `maintenance_request_id`, so a
        # machine with several abnormal readings before the alert resolves
        # safely reuses the same pending draft instead of duplicating it.
        if result.get("requires_maintenance_request"):
            draft = build_maintenance_request_draft(
                maintenance_request_id=result["maintenance_request_id"],
                alert_id=result["alert_id"],
                machine_id=reading.machine_id,
                machine_type=str(reading.machine_type),
                risk_level=result.get("risk_level"),
                maintenance_reason=final_checklist.get("maintenance_reason"),
                manual_id=final_checklist.get("manual_id"),
            )
            await MaintenanceRequestRepository(session).create_draft(draft)

    return {
        "status": "success",
        "reading_id": reading.reading_id,
        "thread_id": thread_id,
        "alert_id": result.get("alert_id"),
        "risk_level": result.get("risk_level"),
        "alert_status": result.get("alert_status"),
        "repeat_count": result.get("repeat_count", 0),
        "awaiting_worker_response": is_awaiting_worker_response,
        "checklist_id": (final_checklist or {}).get("checklist_id"),
        "maintenance_request_id": result.get("maintenance_request_id"),
    }
