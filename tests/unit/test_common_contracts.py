"""Tests that freeze the team-wide enums and sensor contracts."""

import unittest
from datetime import datetime

from pydantic import ValidationError

from app.core.enums import (
    AlertStatus,
    ExperienceLevel,
    MachineType,
    MeasurementMode,
    RiskLevel,
    Shift,
    TrainingStatus,
)
from app.core.exceptions import NotificationError, RAGRetrievalError
from app.models.sensor import SensorReading


def valid_payload() -> dict:
    """Return a minimal valid payload for contract validation tests."""

    return {
        "reading_id": "RD-M0101-20260723T101500",
        "machine_id": "M-0101",
        "machine_type": "REACTOR",
        "measured_at": datetime.fromisoformat("2026-07-23T10:15:00+09:00"),
        "measurement_mode": "PERIODIC",
        "temperature": 41.2,
        "pressure": 43.0,
        "humidity": 56.0,
        "vibration": 3.1,
        "speed": 1200.0,
        "age": 7,
        "service_days": 160,
        "gas": 7.8,
        "sparks": 1,
        "shift": "DAY",
        "experience": "SENIOR",
        "training": "YES",
    }


class EnumContractTest(unittest.TestCase):
    """Protect stable values consumed by graph routing and persistence."""

    def test_core_enum_values(self) -> None:
        self.assertEqual(MachineType.REACTOR.value, "REACTOR")
        self.assertEqual(MeasurementMode.IMMEDIATE_RECHECK.value, "IMMEDIATE_RECHECK")
        self.assertEqual(RiskLevel.EMERGENCY.value, "EMERGENCY")
        self.assertEqual(AlertStatus.MONITORING.value, "MONITORING")
        self.assertEqual(Shift.DAY.value, "Day")
        self.assertEqual(ExperienceLevel.SENIOR.value, "Senior")
        self.assertEqual(TrainingStatus.YES.value, "Yes")

    def test_shared_error_codes(self) -> None:
        self.assertEqual(RAGRetrievalError.error_code, "RAG_RETRIEVAL_FAILED")
        self.assertEqual(NotificationError.error_code, "NOTIFICATION_FAILED")


class SensorContractTest(unittest.TestCase):
    """Verify normalization and cross-field machine validation."""

    def test_categories_are_normalized_to_model_values(self) -> None:
        reading = SensorReading.model_validate(valid_payload())

        self.assertEqual(reading.shift, Shift.DAY)
        self.assertEqual(reading.experience, ExperienceLevel.SENIOR)
        self.assertEqual(reading.training, TrainingStatus.YES)

    def test_machine_id_and_type_must_match(self) -> None:
        payload = valid_payload()
        payload["machine_type"] = "PUMP"

        with self.assertRaises(ValidationError):
            SensorReading.model_validate(payload)

    def test_unknown_fields_are_rejected(self) -> None:
        payload = valid_payload()
        payload["workers"] = 3

        with self.assertRaises(ValidationError):
            SensorReading.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
