"""API routes for Alert state and checklist lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/active/{machine_id}")
async def get_active_alert(
    machine_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Retrieve the currently active (non-RESOLVED) alert for a machine."""
    alert = await AlertRepository(session).get_active_alert_by_machine(machine_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active alert found for machine {machine_id}",
        )
    return alert


@router.get("/{alert_id}/checklist")
async def get_alert_checklist(
    alert_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Retrieve the most recently generated checklist for an alert."""
    alert = await AlertRepository(session).get_by_id(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"alert {alert_id} not found",
        )

    checklists = await ChecklistRepository(session).get_latest_by_alert(alert_id)
    if not checklists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no checklist found for alert {alert_id}",
        )
    return checklists