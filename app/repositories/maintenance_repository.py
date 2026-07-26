"""Repository layer for maintenance-request drafts and manager decisions (FR-14).

Not in the original 12-role contract's `app/repositories/` list, but the team
agreed (2026-07-24) that role C owns this feature end to end - see
`app.api.maintenance_routes` for the API surface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenanceRequestStatus
from app.core.exceptions import DatabaseOperationError
from app.models.orm_models import MaintenanceRequestORM

logger = logging.getLogger(__name__)


class MaintenanceRequestRepository:
    """Handles DB operations for maintenance-request drafts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, maintenance_request_id: str) -> MaintenanceRequestORM | None:
        """Fetch one maintenance-request draft by id."""
        try:
            stmt = select(MaintenanceRequestORM).where(
                MaintenanceRequestORM.maintenance_request_id == maintenance_request_id
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            raise DatabaseOperationError(
                f"Failed to fetch maintenance request {maintenance_request_id}: {exc}",
                details={"maintenance_request_id": maintenance_request_id},
            ) from exc

    async def create_draft(self, draft_data: dict[str, Any]) -> MaintenanceRequestORM:
        """Create a PENDING maintenance-request draft, or return the existing one.

        Idempotent per `maintenance_request_id` (analogous to
        `ChecklistRepository.save_checklist`) - the node that will eventually
        call this (once `action_draft_node`/role B exists) may run again on a
        resumed thread.
        """
        maintenance_request_id = draft_data.get("maintenance_request_id")
        if not maintenance_request_id:
            raise DatabaseOperationError("Cannot create a maintenance request without maintenance_request_id")

        existing = await self.get_by_id(maintenance_request_id)
        if existing is not None:
            return existing

        try:
            orm_obj = MaintenanceRequestORM(
                maintenance_request_id=maintenance_request_id,
                alert_id=draft_data["alert_id"],
                machine_id=draft_data["machine_id"],
                machine_type=draft_data["machine_type"],
                title=draft_data["title"],
                recommendation=draft_data["recommendation"],
                priority=draft_data["priority"],
            )
            self.session.add(orm_obj)
            await self.session.commit()
            await self.session.refresh(orm_obj)
            return orm_obj
        except Exception as exc:
            await self.session.rollback()
            raise DatabaseOperationError(
                f"Failed to create maintenance request draft: {exc}",
                details={"maintenance_request_id": maintenance_request_id},
            ) from exc

    async def list_pending(self) -> list[MaintenanceRequestORM]:
        """List every draft still awaiting a manager decision, newest first."""
        try:
            stmt = (
                select(MaintenanceRequestORM)
                .where(MaintenanceRequestORM.status == MaintenanceRequestStatus.PENDING)
                .order_by(MaintenanceRequestORM.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception as exc:
            raise DatabaseOperationError(f"Failed to list pending maintenance requests: {exc}") from exc

    async def apply_decision(
        self,
        maintenance_request_id: str,
        *,
        decision: MaintenanceRequestStatus,
        decided_by: str | None,
        comment: str | None,
    ) -> MaintenanceRequestORM:
        """Persist a manager's approve/reject/defer decision on an existing draft.

        Callers (see `app.api.maintenance_routes`) are responsible for
        checking the draft exists and is still PENDING before calling this -
        those are HTTP-semantics concerns (404/409), not persistence failures.
        """
        record = await self.get_by_id(maintenance_request_id)
        if record is None:
            raise DatabaseOperationError(
                f"maintenance request {maintenance_request_id} not found",
                details={"maintenance_request_id": maintenance_request_id},
            )

        try:
            record.status = decision
            record.decided_by = decided_by
            record.decision_comment = comment
            record.decided_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(record)
            return record
        except Exception as exc:
            await self.session.rollback()
            raise DatabaseOperationError(
                f"Failed to save maintenance request decision: {exc}",
                details={"maintenance_request_id": maintenance_request_id},
            ) from exc
