"""Integration and unit tests for role C (backend / DB engineer)."""

from datetime import datetime, timezone

import pytest

from app.core import db
from app.core.enums import (
    AlertStatus,
    ExperienceLevel,
    MachineType,
    MeasurementMode,
    RiskLevel,
    Shift,
    TrainingStatus,
)
from app.models.orm_models import Base
from app.models.sensor import SensorReading
from app.nodes.persistence import save_alert_state, save_sensor_reading
from app.repositories.alert_repository import AlertRepository
from app.repositories.sensor_repository import SensorRepository


@pytest.fixture
async def async_session():
    """Point the shared DB engine at a fresh in-memory SQLite DB for this test.

    `db.configure(...)` rebuilds the module-level engine that both this
    fixture and the persistence nodes under test read from via
    `db.session_scope()` — so the node's writes and this fixture's reads
    land in the same database instead of two unrelated ones.
    """

    db.configure("sqlite+aiosqlite:///:memory:")
    engine = db.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db.session_scope() as session:
        yield session

    await engine.dispose()


def test_sensor_reading_validation():
    raw_payload = {
        "reading_id": "RD-M0101-20260723",
        "machine_id": "M-0101",
        "machine_type": "REACTOR",
        "measured_at": datetime.now(timezone.utc),
        "measurement_mode": "PERIODIC",
        "temperature": 85.5,
        "pressure": 3.2,
        "humidity": 40.0,
        "vibration": 0.12,
        "speed": 1500.0,
        "age": 3,
        "service_days": 120,
        "gas": 0.01,
        "sparks": 0,
        "shift": "day",  # 대소문자 정규화 테스트
        "experience": "senior",
        "training": "yes",
    }
    reading = SensorReading(**raw_payload)
    assert reading.shift == Shift.DAY
    assert reading.experience == ExperienceLevel.SENIOR
    assert reading.training == TrainingStatus.YES


@pytest.mark.asyncio
async def test_save_sensor_reading_node(async_session):
    mock_state = {
        "reading_id": "RD-M0101-001",
        "sensor_reading": {
            "reading_id": "RD-M0101-001",
            "machine_id": "M-0101",
            "machine_type": MachineType.REACTOR,
            "measured_at": datetime.now(timezone.utc),
            "measurement_mode": MeasurementMode.PERIODIC,
            "temperature": 90.0,
            "pressure": 4.0,
            "humidity": 30.0,
            "vibration": 0.2,
            "speed": 1600.0,
            "age": 2,
            "service_days": 90,
            "gas": 0.05,
            "sparks": 1,
            "shift": Shift.NIGHT,
            "experience": ExperienceLevel.JUNIOR,
            "training": TrainingStatus.NO,
        },
    }

    result = await save_sensor_reading(mock_state)
    assert result == {}  # node contract: only changed fields (none here)

    sensor_repo = SensorRepository(async_session)
    db_record = await sensor_repo.get_by_id("RD-M0101-001")
    assert db_record is not None
    assert db_record.temperature == 90.0


@pytest.mark.asyncio
async def test_save_alert_state_node(async_session):
    mock_state = {
        "alert_id": "AL-M0101-001",
        "thread_id": "M-0101:AL-M0101-001",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "reading_id": "RD-M0101-001",
        "risk_level": RiskLevel.WARNING,
        "alert_status": AlertStatus.OPEN,
        "repeat_count": 1,
        "consecutive_normal_count": 0,
        "emergency_reasons": ["High Temperature Threshold Exceeded"],
    }

    result = await save_alert_state(mock_state)
    assert result == {}

    alert_repo = AlertRepository(async_session)
    active_alert = await alert_repo.get_active_alert_by_machine("M-0101")
    assert active_alert is not None
    assert active_alert.alert_id == "AL-M0101-001"
    assert active_alert.risk_level == RiskLevel.WARNING


@pytest.mark.asyncio
async def test_save_sensor_reading_node_missing_reading_is_a_noop(async_session):
    """A node must never raise on a merely-empty optional input."""

    result = await save_sensor_reading({"reading_id": "RD-M0101-002"})
    assert result == {}
