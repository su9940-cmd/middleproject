"""Repository layer for checklist generation and worker responses."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseOperationError
from app.models.orm_models import ChecklistORM

logger = logging.getLogger(__name__)


class ChecklistRepository:
    """Handles DB operations for Action Checklists and HITL responses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, checklist_id: str) -> ChecklistORM | None:
        """Fetch one checklist row by id."""
        try:
            stmt = select(ChecklistORM).where(ChecklistORM.checklist_id == checklist_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            raise DatabaseOperationError(
                f"Failed to fetch checklist {checklist_id}: {exc}",
                details={"checklist_id": checklist_id},
            ) from exc

    async def get_latest_by_alert(self, alert_id: str) -> ChecklistORM | None:
        """Fetch the highest-`version` checklist generated for an alert, if any."""
        try:
            stmt = (
                select(ChecklistORM)
                .where(ChecklistORM.alert_id == alert_id)
                .order_by(ChecklistORM.version.desc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            raise DatabaseOperationError(
                f"Failed to fetch latest checklist for alert {alert_id}: {exc}",
                details={"alert_id": alert_id},
            ) from exc

    async def save_checklist(self, checklist_data: dict[str, Any]) -> ChecklistORM:
        """Save the checklist Validator Agent just generated.

        Idempotent: `validator_agent` may run again on a resumed thread (see
        `langgraph.types.interrupt`'s "re-executes the whole node" behavior
        further downstream at `worker_interrupt`), so a second call with the
        same `checklist_id` returns the already-saved row instead of
        violating the primary key.
        """
        checklist_id = checklist_data.get("checklist_id")
        if not checklist_id:
            raise DatabaseOperationError("Cannot save a checklist without checklist_id")

        existing = await self.get_by_id(checklist_id)
        if existing is not None:
            return existing

        try:
            orm_obj = ChecklistORM(
                checklist_id=checklist_id,
                alert_id=checklist_data["alert_id"],
                version=checklist_data.get("version", 1),
                risk_level=checklist_data.get("risk_level", "CAUTION"),
                action_phase=checklist_data.get("action_phase", "INITIAL"),
                items=checklist_data.get("items", []),
                requires_manager_report=checklist_data.get("requires_manager_report", False),
                requires_maintenance_request=checklist_data.get("requires_maintenance_request", False),
            )
            self.session.add(orm_obj)
            await self.session.commit()
            await self.session.refresh(orm_obj)
            return orm_obj
        except Exception as exc:
            await self.session.rollback()
            raise DatabaseOperationError(
                f"Failed to save checklist: {exc}",
                details={"checklist_id": checklist_id},
            ) from exc

    async def update_worker_response(
        self, checklist_id: str, worker_response: dict[str, Any]
    ) -> ChecklistORM:
        """Update checklist with worker's completion notes and status."""
        try:
            stmt = select(ChecklistORM).where(ChecklistORM.checklist_id == checklist_id)
            result = await self.session.execute(stmt)
            checklist = result.scalar_one_or_none()

            if not checklist:
                raise DatabaseOperationError(f"Checklist {checklist_id} not found")

            # Update worker responses
            checklist.items = worker_response.get("items", checklist.items)
            checklist.worker_note = worker_response.get("worker_note")
            checklist.completed_at = datetime.now(timezone.utc)

            await self.session.commit()
            await self.session.refresh(checklist)
            return checklist
        except Exception as exc:
            await self.session.rollback()
            raise DatabaseOperationError(
                f"Failed to update worker response: {exc}",
                details={"checklist_id": checklist_id},
            ) from exc