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
    MaintenanceRequestStatus,
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

    # `values_callable` is required here: SQLAlchemy's `Enum` type stores the
    # Python member *name* by default (e.g. "DAY"), but Shift/ExperienceLevel/
    # TrainingStatus have name != value ("DAY" vs "Day") - without this the
    # DB would silently store "DAY"/"JUNIOR"/"YES" instead of the shared
    # contract's actual "Day"/"Junior"/"Yes" (round-trips fine through the
    # ORM either way, but a raw SQL read would see the wrong casing).
    shift: Mapped[Shift] = mapped_column(
        Enum(Shift, values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
    )
    experience: Mapped[ExperienceLevel] = mapped_column(
        Enum(ExperienceLevel, values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
    )
    training: Mapped[TrainingStatus] = mapped_column(
        Enum(TrainingStatus, values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
    )

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


class MaintenanceRequestORM(Base):
    """DB table for maintenance-request drafts awaiting manager approval (FR-14).

    Kept separate from `AlertORM` (one alert may or may not have a draft, and
    its approval lifecycle is independent of the alert's own lifecycle) per
    the 2026-07-24 team decision.
    """

    __tablename__ = "maintenance_requests"

    maintenance_request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    machine_type: Mapped[MachineType] = mapped_column(Enum(MachineType), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[MaintenanceRequestStatus] = mapped_column(
        Enum(MaintenanceRequestStatus), default=MaintenanceRequestStatus.PENDING, nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )