"""Tests for the persisted model adapter and Predictive Agent."""

import unittest
from datetime import datetime

from app.agents.predictive import get_ml_service, predictive_agent
from app.core.enums import MachineType, MeasurementMode
from app.models.sensor import SensorReading
from app.services.ml_service import MLService


def reactor_reading() -> SensorReading:
    """Return a valid reactor reading matching the trained feature schema."""

    return SensorReading(
        reading_id="RD-M0101-20260723T101500",
        machine_id="M-0101",
        machine_type=MachineType.REACTOR,
        measured_at=datetime.fromisoformat("2026-07-23T10:15:00+09:00"),
        measurement_mode=MeasurementMode.PERIODIC,
        temperature=41.2,
        pressure=43.0,
        humidity=56.0,
        vibration=3.1,
        speed=1200.0,
        age=7,
        service_days=160,
        gas=7.8,
        sparks=1,
        shift="Day",
        experience="Senior",
        training="Yes",
    )


class MLServiceTest(unittest.TestCase):
    """Exercise the actual persisted sklearn pipeline."""

    def test_predict_returns_probability_and_metadata_thresholds(self) -> None:
        prediction = MLService().predict(reactor_reading())

        self.assertGreaterEqual(prediction.ml_risk_score, 0.0)
        self.assertLessEqual(prediction.ml_risk_score, 1.0)
        self.assertAlmostEqual(prediction.prediction_thresholds["caution"], 0.145)
        self.assertAlmostEqual(prediction.prediction_thresholds["warning"], 0.29)
        self.assertTrue(prediction.model_version)


class PredictiveAgentTest(unittest.TestCase):
    """Verify the LangGraph node input and output contract."""

    def tearDown(self) -> None:
        get_ml_service.cache_clear()

    def test_agent_returns_only_prediction_and_error_fields(self) -> None:
        reading = reactor_reading()
        result = predictive_agent(
            {
                "reading_id": reading.reading_id,
                "machine_id": reading.machine_id,
                "machine_type": reading.machine_type,
                "measured_at": reading.measured_at,
                "measurement_mode": reading.measurement_mode,
                "sensor_reading": reading.model_dump(mode="python"),
            }
        )

        self.assertIn("ml_risk_score", result)
        self.assertEqual(result["failed_node"], None)
        self.assertNotIn("risk_level", result)

    def test_agent_reports_missing_sensor_reading(self) -> None:
        result = predictive_agent({"machine_id": "M-0101"})

        self.assertEqual(result["error_code"], "SENSOR_VALIDATION_FAILED")
        self.assertEqual(result["failed_node"], "predictive_agent")


if __name__ == "__main__":
    unittest.main()
