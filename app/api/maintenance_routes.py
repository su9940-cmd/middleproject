"""API routes for maintenance-request approval (FR-14).

Not in the original 12-role contract (`ManagerReviewScreen.jsx`/role E calls
this out as unassigned in its own docstring) - the team agreed 2026-07-24
that role C owns it. AI only ever drafts a maintenance request
(`requires_maintenance_request`); a manager's approve/reject/defer decision
here is what actually confirms or discards it.

Convention (2026-07-24 team decision): external JSON is camelCase, internal
DB/Python fields stay snake_case - enforced via `alias_generator=to_camel`
below rather than hand-written aliases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.enums import MaintenanceRequestStatus
from app.repositories.maintenance_repository import MaintenanceRequestRepository

router = APIRouter(prefix="/maintenance-requests", tags=["Maintenance Requests"])


class MaintenanceRequestResponse(BaseModel):
    """API response shape for one maintenance-request draft (camelCase on the wire)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    maintenance_request_id: str
    alert_id: str
    machine_id: str
    machine_type: str
    title: str
    recommendation: str
    priority: str
    status: str
    decided_by: str | None
    decision_comment: str | None
    decided_at: datetime | None
    created_at: datetime


class MaintenanceDecisionRequest(BaseModel):
    """Request body for `POST /maintenance-requests/{id}/decision` (camelCase on the wire)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    maintenance_decision: Literal["APPROVED", "REJECTED", "DEFERRED"]
    decided_by: str | None = None
    comment: str | None = None


@router.get("/pending", response_model=list[MaintenanceRequestResponse])
async def list_pending_maintenance_requests(
    session: AsyncSession = Depends(get_db_session),
) -> list[MaintenanceRequestResponse]:
    """List every maintenance-request draft still awaiting a manager decision."""

    records = await MaintenanceRequestRepository(session).list_pending()
    return [MaintenanceRequestResponse.model_validate(record) for record in records]


@router.post("/{maintenance_request_id}/decision", response_model=MaintenanceRequestResponse)
async def decide_maintenance_request(
    maintenance_request_id: str,
    payload: MaintenanceDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MaintenanceRequestResponse:
    """Apply a manager's approve/reject/defer decision to a pending draft (FR-14)."""

    repo = MaintenanceRequestRepository(session)
    record = await repo.get_by_id(maintenance_request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"maintenance request {maintenance_request_id} not found",
        )
    if record.status != MaintenanceRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"maintenance request {maintenance_request_id} already decided ({record.status.value})",
        )

    updated = await repo.apply_decision(
        maintenance_request_id,
        decision=MaintenanceRequestStatus(payload.maintenance_decision),
        decided_by=payload.decided_by,
        comment=payload.comment,
    )
    return MaintenanceRequestResponse.model_validate(updated)
