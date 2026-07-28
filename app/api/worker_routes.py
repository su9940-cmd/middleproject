"""API routes for worker response and checklist completion.

`POST /worker/checklists/{checklist_id}/respond` is the resume side of
`app.nodes.worker_interrupt.worker_interrupt`: it resolves the checklist's
owning alert/machine to rebuild `thread_id` (`{machine_id}:{alert_id}`, see
`app.core.ids`), then resumes the same LangGraph run that paused there via
`Command(resume=...)`. That run continues straight into
`request_immediate_recheck` and stops, so the response persisted here is
`alert_status=WAITING_RECHECK` plus the worker's own answers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.enums import AlertStatus
from app.core.exceptions import WorkerResponseSaveError
from app.core.ids import build_thread_id
from app.nodes.persistence import save_alert_state, save_worker_response
from app.models.worker import WorkerResumePayload
from app.nodes.worker_interrupt import _validate_item_results
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository

router = APIRouter(prefix="/worker", tags=["Worker Responses"])


def get_safety_graph(request: Request) -> CompiledStateGraph:
    """Fetch the graph compiled once at startup (see `main.py`'s `lifespan`)."""

    return request.app.state.safety_graph


async def _recover_worker_response_without_graph(
    *,
    checklist_id: str,
    payload: dict[str, Any],
    checklist: Any,
    alert: Any,
    session: AsyncSession,
    thread_id: str,
) -> dict[str, Any]:
    """Persist a valid response when the in-memory graph checkpoint is stale."""

    if checklist.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"checklist {checklist_id} has already been submitted",
        )
    try:
        response = WorkerResumePayload.model_validate(payload)
        if response.alert_id != alert.alert_id:
            raise ValueError("worker response alert_id does not match the checklist alert")
        if response.checklist_id != checklist_id:
            raise ValueError("worker response checklist_id does not match the requested checklist")
        _validate_item_results(response, {"items": checklist.items})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid worker response: {exc}",
        ) from exc

    normalized_response = response.model_dump(mode="json")
    await ChecklistRepository(session).update_worker_response(checklist_id, normalized_response)
    await AlertRepository(session).upsert_alert_state(
        {
            "alert_id": alert.alert_id,
            "thread_id": thread_id,
            "machine_id": alert.machine_id,
            "machine_type": alert.machine_type,
            "reading_id": alert.reading_id,
            "risk_level": alert.risk_level,
            "alert_status": AlertStatus.WAITING_RECHECK,
            "repeat_count": alert.repeat_count,
            "consecutive_normal_count": alert.consecutive_normal_count,
            "emergency_reasons": alert.emergency_reasons or [],
            "notification_status": alert.notification_status,
            "requires_maintenance_request": alert.requires_maintenance_request,
            "maintenance_request_id": alert.maintenance_request_id,
        }
    )
    return {
        "status": "success",
        "checklist_id": checklist_id,
        "thread_id": thread_id,
        "alert_status": AlertStatus.WAITING_RECHECK,
        "recheck_requested_at": datetime.now(timezone.utc),
        "recovered_without_graph_state": True,
    }


@router.post("/checklists/{checklist_id}/respond")
async def submit_worker_response(
    checklist_id: str,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
    graph: CompiledStateGraph = Depends(get_safety_graph),
) -> dict[str, Any]:
    """Resume the paused safety graph with a worker's checklist response."""

    checklist = await ChecklistRepository(session).get_by_id(checklist_id)
    if checklist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"checklist {checklist_id} not found",
        )

    alert = await AlertRepository(session).get_by_id(checklist.alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"alert {checklist.alert_id} not found",
        )

    thread_id = build_thread_id(alert.machine_id, alert.alert_id)
    config = {"configurable": {"thread_id": thread_id}}

    snapshot = await graph.aget_state(config)
    if "worker_interrupt" not in snapshot.next:
        return await _recover_worker_response_without_graph(
            checklist_id=checklist_id,
            payload=payload,
            checklist=checklist,
            alert=alert,
            session=session,
            thread_id=thread_id,
        )

    worker_response = {"checklist_id": checklist_id, **payload}

    try:
        result = await graph.ainvoke(Command(resume=worker_response), config=config)
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        # A second checklist can be generated while an older interrupt is
        # still held in the in-memory checkpoint. In that case the graph sees
        # a different item-ID set than the DB/UI checklist. Persist the valid
        # DB checklist response and continue with an immediate recheck.
        if "checklist items do not match" in str(exc) or "checklist_id does not match" in str(exc):
            return await _recover_worker_response_without_graph(
                checklist_id=checklist_id,
                payload=payload,
                checklist=checklist,
                alert=alert,
                session=session,
                thread_id=thread_id,
            )
        raise WorkerResponseSaveError(
            f"failed to resume graph for checklist {checklist_id}: {exc}",
            details={"checklist_id": checklist_id},
        ) from exc

    if result.get("error_code"):
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "checklist_id": checklist_id,
                "error_code": result.get("error_code"),
                "message": result.get("error_message"),
                "failed_node": result.get("failed_node"),
            },
        )

    await save_worker_response(result)
    if result.get("alert_status") not in (None, AlertStatus.NONE):
        await save_alert_state(result)

    return {
        "status": "success",
        "checklist_id": checklist_id,
        "thread_id": thread_id,
        "alert_status": result.get("alert_status"),
        "recheck_requested_at": result.get("recheck_requested_at"),
    }
