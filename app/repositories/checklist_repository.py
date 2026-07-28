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
        """Fetch the highest-`version` checklist generated for an alert, if any.

        `version` only counts the validator's revision loop within a single
        action_draft call, so it resets to 1 on every fresh draft occasion -
        a still-open alert that recurs (e.g. MONITORING -> abnormal again,
        same alert_id reused - see `alert_lifecycle_node`) produces another
        version-1 checklist alongside the first. `created_at` breaks that tie
        in favor of the actually-latest row instead of an arbitrary one.
        """
        try:
            stmt = (
                select(ChecklistORM)
                .where(ChecklistORM.alert_id == alert_id)
                .order_by(ChecklistORM.version.desc(), ChecklistORM.created_at.desc())
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
                supporting_references=checklist_data.get("supporting_references", []),
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
        """Apply a worker's per-item statuses/notes and the overall note to a saved checklist.

        `worker_response` is `state["worker_response"]` - the validated
        `WorkerResumePayload` dump (`app.models.worker`) produced by
        `app.nodes.worker_interrupt`: `item_results: [{checklist_item_id,
        status, worker_note}]` plus a top-level `overall_note`. The older
        compact `{"item_statuses": {id: status}, "note": str}` shape (the
        pre-normalization raw resume payload) is still accepted directly,
        since callers may invoke this repository outside the graph.

        Only `status`/`worker_note` are merged into each stored item (not the
        whole item object), so `title`/`instruction`/`citations`/etc. are
        never dropped.
        """
        try:
            stmt = select(ChecklistORM).where(ChecklistORM.checklist_id == checklist_id)
            result = await self.session.execute(stmt)
            checklist = result.scalar_one_or_none()

            if not checklist:
                raise DatabaseOperationError(f"Checklist {checklist_id} not found")

            item_updates: dict[str, dict[str, Any]] = {}
            for item in worker_response.get("item_results") or []:
                if isinstance(item, dict) and item.get("checklist_item_id"):
                    item_updates[item["checklist_item_id"]] = {
                        "status": item.get("status"),
                        "worker_note": item.get("worker_note"),
                    }
            for item_id, status in (worker_response.get("item_statuses") or {}).items():
                item_updates.setdefault(item_id, {})["status"] = status

            checklist.items = [
                {**item, **item_updates[item["checklist_item_id"]]}
                if item.get("checklist_item_id") in item_updates
                else item
                for item in checklist.items
            ]
            checklist.worker_note = worker_response.get("overall_note") or worker_response.get("note")
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
