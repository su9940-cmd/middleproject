"""Repository layer for Alert incident lifecycle management."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseOperationError
from app.models.orm_models import AlertORM

logger = logging.getLogger(__name__)


class AlertRepository:
    """Handles database operations for Alert state and history."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_alert_state(self, alert_data: dict[str, Any]) -> AlertORM:
        """Create or update an alert state in DB."""
        alert_id = alert_data.get("alert_id")
        if not alert_id:
            raise DatabaseOperationError("Cannot upsert alert without alert_id")

        try:
            stmt = select(AlertORM).where(AlertORM.alert_id == alert_id)
            result = await self.session.execute(stmt)
            existing_alert = result.scalar_one_or_none()

            if existing_alert:
                # Update existing alert fields
                for key, value in alert_data.items():
                    if hasattr(existing_alert, key) and value is not None:
                        setattr(existing_alert, key, value)
                orm_obj = existing_alert
            else:
                # Create new alert entry
                orm_obj = AlertORM(**alert_data)
                self.session.add(orm_obj)

            await self.session.commit()
            await self.session.refresh(orm_obj)
            return orm_obj

        except Exception as exc:
            await self.session.rollback()
            logger.error("Failed to upsert alert state for %s: %s", alert_id, exc, exc_info=True)
            raise DatabaseOperationError(
                f"Failed to save alert state: {exc}",
                details={"alert_id": alert_id},
            ) from exc

    async def get_by_id(self, alert_id: str) -> AlertORM | None:
        """Fetch one alert row by its id, regardless of lifecycle status."""
        try:
            stmt = select(AlertORM).where(AlertORM.alert_id == alert_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            raise DatabaseOperationError(
                f"Failed to fetch alert {alert_id}: {exc}",
                details={"alert_id": alert_id},
            ) from exc

    async def get_active_alert_by_machine(self, machine_id: str) -> AlertORM | None:
        """Get currently unresolved alert for a specific machine."""
        try:
            stmt = (
                select(AlertORM)
                .where(AlertORM.machine_id == machine_id)
                .where(AlertORM.alert_status != "RESOLVED")
                .order_by(AlertORM.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return result.scalars().first()
        except Exception as exc:
            raise DatabaseOperationError(
                f"Failed to fetch active alert for machine: {exc}",
                details={"machine_id": machine_id},
            ) from exc