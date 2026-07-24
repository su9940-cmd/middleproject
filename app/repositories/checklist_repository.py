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

    async def save_checklist(self, checklist_data: dict[str, Any]) -> ChecklistORM:
        """Save newly generated checklist from Validator Agent."""
        checklist_id = checklist_data.get("checklist_id")
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