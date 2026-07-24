"""API routes for Alert state and checklist lookup."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseOperationError
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository

# async_session_dependency는 DB 세션 주입용 의존성 (환경에 맞게 연결)
from app.core.db import get_db_session

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/active/{machine_id}")
async def get_active_alert(
    machine_id: str,
    session: AsyncSession = Depends(get_db_session),
):
    """Retrieve currently active alert for a given machine."""
    repo = AlertRepository(session)
    alert = await repo.get_active_alert_by_machine(machine_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active alert found for machine {machine_id}",
        )
    return alert