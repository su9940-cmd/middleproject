"""Validated IoT sensor input models."""

from datetime import datetime
from math import isfinite

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums import MachineType, MeasurementMode


class SensorReading(BaseModel):
    """One periodic or immediate-recheck reading for a single machine."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reading_id: str
    machine_id: str
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

    shift: str
    experience: str
    training: str

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
