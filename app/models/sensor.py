"""Validated IoT sensor input models."""

from datetime import datetime
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ExperienceLevel,
    MachineType,
    MeasurementMode,
    Shift,
    TrainingStatus,
)


MACHINE_ID_TYPE_MAP = {
    "M-0101": MachineType.REACTOR,
    "M-0102": MachineType.COMPRESSOR,
    "M-0103": MachineType.STORAGE_TANK,
    "M-0104": MachineType.PUMP,
}


class SensorReading(BaseModel):
    """One periodic or immediate-recheck reading for a single machine."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reading_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    machine_type: MachineType
    measured_at: datetime
    measurement_mode: MeasurementMode

    temperature: float
    pressure: float
    humidity: float
    vibration: float
    speed: float
    age: int
    service_days: int
    gas: float
    sparks: int

    shift: Shift
    experience: ExperienceLevel
    training: TrainingStatus

    @field_validator("shift", "experience", "training", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> object:
        """Accept category strings case-insensitively and store model values."""

        if not isinstance(value, str):
            return value
        normalized = value.strip().casefold()
        category_values = {
            "day": Shift.DAY,
            "night": Shift.NIGHT,
            "junior": ExperienceLevel.JUNIOR,
            "senior": ExperienceLevel.SENIOR,
            "yes": TrainingStatus.YES,
            "no": TrainingStatus.NO,
        }
        return category_values.get(normalized, value)

    @field_validator(
        "temperature",
        "pressure",
        "humidity",
        "vibration",
        "speed",
        "gas",
    )
    @classmethod
    def validate_finite_number(cls, value: float) -> float:
        """Reject NaN and infinite readings before model inference."""

        if not isfinite(value):
            raise ValueError("sensor values must be finite")
        return value

    @field_validator("age", "service_days", "sparks")
    @classmethod
    def validate_non_negative_integer(cls, value: int) -> int:
        """Reject negative count and age values."""

        if value < 0:
            raise ValueError("integer sensor/context values must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_machine_identity(self) -> "SensorReading":
        """Ensure the fixed demo machine ID and machine type agree."""

        expected_type = MACHINE_ID_TYPE_MAP.get(self.machine_id)
        if expected_type is None:
            raise ValueError(f"unsupported machine_id: {self.machine_id}")
        if self.machine_type != expected_type:
            raise ValueError(
                f"machine_id {self.machine_id} requires machine_type {expected_type.value}"
            )
        return self
