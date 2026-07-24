"""API routes for worker response and checklist completion."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import WorkerResponseSaveError
from app.repositories.checklist_repository import ChecklistRepository
from app.core.db import get_db_session

router = APIRouter(prefix="/worker", tags=["Worker Responses"])


@router.post("/checklists/{checklist_id}/respond")
async def submit_worker_response(
    checklist_id: str,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
):
    """Submit worker action checklist completion responses."""
    repo = ChecklistRepository(session)
    try:
        updated_checklist = await repo.update_worker_response(checklist_id, payload)
        return {
            "status": "success",
            "checklist_id": updated_checklist.checklist_id,
            "message": "Worker response saved successfully.",
        }
    except Exception as exc:
        raise WorkerResponseSaveError(
            f"Failed to submit worker response: {exc}",
            details={"checklist_id": checklist_id},
        ) from exc