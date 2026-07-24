"""Repository layer for sensor data CRUD operations."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DatabaseOperationError
from app.models.orm_models import SensorReadingORM

logger = logging.getLogger(__name__)


class SensorRepository:
    """Handles database access for sensor readings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_sensor_reading(self, reading_data: dict[str, Any]) -> SensorReadingORM:
        """Persist a new sensor reading to DB."""
        try:
            orm_obj = SensorReadingORM(**reading_data)
            self.session.add(orm_obj)
            await self.session.commit()
            await self.session.refresh(orm_obj)
            return orm_obj
        except Exception as exc:
            await self.session.rollback()
            logger.error("Failed to save sensor reading: %s", exc, exc_info=True)
            raise DatabaseOperationError(
                f"Failed to insert sensor reading: {exc}",
                details={"reading_id": reading_data.get("reading_id")},
            ) from exc

    async def get_by_id(self, reading_id: str) -> SensorReadingORM | None:
        """Retrieve sensor reading by reading_id."""
        try:
            stmt = select(SensorReadingORM).where(SensorReadingORM.reading_id == reading_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as exc:
            logger.error("Failed to fetch sensor reading %s: %s", reading_id, exc)
            raise DatabaseOperationError(
                f"Failed to query sensor reading: {exc}",
                details={"reading_id": reading_id},
            ) from exc