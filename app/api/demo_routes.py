"""Demo-only reset endpoint used by the UI during local presentations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.enums import ExperienceLevel, MachineType, MeasurementMode, Shift, TrainingStatus
from app.graph.builder import build_safety_graph, default_graph_dependencies
from app.models.orm_models import Base, SensorReadingORM

router = APIRouter(prefix="/demo", tags=["Demo"])

_NORMAL_MACHINES = (
    ("M-0101", MachineType.REACTOR),
    ("M-0102", MachineType.COMPRESSOR),
    ("M-0103", MachineType.STORAGE_TANK),
    ("M-0104", MachineType.PUMP),
)

# 초기화 직후에도 기기별 정상 센서값이 모두 같아 보이지 않도록 하는
# 고정된 정상 범위 샘플. 매번 초기화해도 위험 규칙을 넘지 않으면서
# 기기 특성 차이가 화면에 드러남.
_NORMAL_SENSOR_VALUES = {
    "M-0101": {"temperature": 26.0, "pressure": 21.0, "humidity": 41.0, "vibration": 0.7, "speed": 1180.0, "service_days": 82, "gas": 0.8},
    "M-0102": {"temperature": 24.5, "pressure": 23.0, "humidity": 39.0, "vibration": 0.9, "speed": 1230.0, "service_days": 96, "gas": 1.2},
    "M-0103": {"temperature": 27.5, "pressure": 20.0, "humidity": 44.0, "vibration": 0.6, "speed": 1160.0, "service_days": 75, "gas": 1.6},
    "M-0104": {"temperature": 25.0, "pressure": 22.0, "humidity": 42.0, "vibration": 0.5, "speed": 1210.0, "service_days": 103, "gas": 0.6},
}


@router.post("/reset")
async def reset_demo_state(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Clear all demo tables and seed one normal reading per machine."""

    for table in reversed(Base.metadata.sorted_tables):
        await session.execute(table.delete())

    reset_at = datetime.now(timezone.utc).replace(microsecond=0)
    readings: list[SensorReadingORM] = []
    for index, (machine_id, machine_type) in enumerate(_NORMAL_MACHINES, start=1):
        measured_at = reset_at - timedelta(minutes=(4 - index) * 15)
        normal = _NORMAL_SENSOR_VALUES[machine_id]
        readings.append(
            SensorReadingORM(
                reading_id=f"RESET-{machine_id.replace('-', '')}-{reset_at:%Y%m%dT%H%M%S}",
                machine_id=machine_id,
                machine_type=machine_type,
                measured_at=measured_at,
                measurement_mode=MeasurementMode.PERIODIC,
                temperature=normal["temperature"],
                pressure=normal["pressure"],
                humidity=normal["humidity"],
                vibration=normal["vibration"],
                speed=normal["speed"],
                age=3,
                service_days=normal["service_days"],
                gas=normal["gas"],
                sparks=0,
                shift=Shift.DAY,
                experience=ExperienceLevel.SENIOR,
                training=TrainingStatus.YES,
            )
        )

    session.add_all(readings)
    await session.commit()
    request.app.state.safety_graph = build_safety_graph(
        default_graph_dependencies(use_database_memory=True)
    )

    return {
        "status": "success",
        "reset_at": reset_at,
        "machine_count": len(readings),
        "reading_ids": [reading.reading_id for reading in readings],
    }
