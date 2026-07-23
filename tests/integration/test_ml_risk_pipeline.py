"""End-to-end test from a sensor reading through ML and risk policy."""

import unittest
from datetime import datetime

from app.agents.predictive import get_ml_service, predictive_agent
from app.core.enums import MachineType, MeasurementMode, RiskLevel
from app.models.sensor import SensorReading
from app.nodes.risk_policy import risk_policy


class MLRiskPipelineIntegrationTest(unittest.TestCase):
    """Verify that the two D-owned nodes share a compatible state contract."""

    def tearDown(self) -> None:
        get_ml_service.cache_clear()

    def test_predictive_output_flows_into_risk_policy(self) -> None:
        reading = SensorReading(
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
        state = {
            "machine_id": reading.machine_id,
            "machine_type": reading.machine_type,
            "sensor_reading": reading.model_dump(mode="json"),
        }

        prediction = predictive_agent(state)
        state.update(prediction)
        decision = risk_policy(state)

        self.assertIsNone(prediction["error_code"])
        self.assertIsNone(decision["error_code"])
        self.assertIn(decision["risk_level"], set(RiskLevel))
        self.assertEqual(decision["policy_version"], "demo-risk-policy-v1")


if __name__ == "__main__":
    unittest.main()
