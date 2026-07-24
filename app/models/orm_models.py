"""SQLAlchemy ORM models for database persistence."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.enums import (
    AlertStatus,
    ChecklistItemStatus,
    ExperienceLevel,
    MachineType,
    MeasurementMode,
    NotificationStatus,
    RiskLevel,
    Shift,
    TrainingStatus,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


class SensorReadingORM(Base):
    """DB Table for storing raw and validated IoT sensor readings."""

    __tablename__ = "sensor_readings"

    reading_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    machine_type: Mapped[MachineType] = mapped_column(Enum(MachineType), nullable=False)

    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measurement_mode: Mapped[MeasurementMode] = mapped_column(Enum(MeasurementMode), nullable=False)

    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    vibration: Mapped[float] = mapped_column(Float, nullable=False)
    speed: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    service_days: Mapped[int] = mapped_column(Integer, nullable=False)
    gas: Mapped[float] = mapped_column(Float, nullable=False)
    sparks: Mapped[int] = mapped_column(Integer, nullable=False)

    shift: Mapped[Shift] = mapped_column(Enum(Shift), nullable=False)
    experience: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    training: Mapped[TrainingStatus] = mapped_column(Enum(TrainingStatus), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AlertORM(Base):
    """DB Table for managing Alert incident lifecycle."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    machine_type: Mapped[MachineType] = mapped_column(Enum(MachineType), nullable=False)
    reading_id: Mapped[str] = mapped_column(String(64), nullable=False)

    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    alert_status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus), default=AlertStatus.OPEN, nullable=False
    )

    repeat_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_normal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    emergency_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notification_status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus), default=NotificationStatus.NOT_REQUIRED, nullable=False
    )

    requires_maintenance_request: Mapped[bool] = mapped_column(default=False, nullable=False)
    maintenance_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ChecklistORM(Base):
    """DB Table for final verified action checklists and worker responses."""

    __tablename__ = "checklists"

    checklist_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    action_phase: Mapped[str] = mapped_column(String(32), nullable=False)

    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    worker_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    requires_manager_report: Mapped[bool] = mapped_column(default=False, nullable=False)
    requires_maintenance_request: Mapped[bool] = mapped_column(default=False, nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )