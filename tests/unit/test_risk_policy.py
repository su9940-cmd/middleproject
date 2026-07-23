"""Tests for deterministic risk classification and emergency overrides."""

import unittest

from app.core.enums import MachineType, RiskLevel
from app.graph.routes import route_by_risk
from app.nodes.risk_policy import risk_policy


def state_for(
    machine_type: MachineType,
    *,
    score: float = 0.1,
    sensor: dict | None = None,
) -> dict:
    """Build a valid policy state with safe default sensor values."""

    defaults = {
        MachineType.REACTOR: {
            "temperature": 30.0,
            "pressure": 25.0,
            "gas": 2.0,
            "sparks": 0,
        },
        MachineType.COMPRESSOR: {
            "vibration": 1.0,
            "speed": 2000.0,
            "pressure": 25.0,
        },
        MachineType.STORAGE_TANK: {
            "gas": 2.0,
            "sparks": 0,
            "pressure": 25.0,
        },
        MachineType.PUMP: {
            "vibration": 1.0,
            "pressure": 25.0,
        },
    }
    return {
        "machine_type": machine_type,
        "ml_risk_score": score,
        "prediction_thresholds": {"caution": 0.145, "warning": 0.29},
        "sensor_reading": sensor or defaults[machine_type],
    }


class RiskPolicyTest(unittest.TestCase):
    """Verify thresholds, emergency rules, and failure behavior."""

    def test_ml_threshold_levels(self) -> None:
        cases = (
            (0.10, RiskLevel.NORMAL),
            (0.145, RiskLevel.CAUTION),
            (0.289, RiskLevel.CAUTION),
            (0.29, RiskLevel.WARNING),
        )
        for score, expected in cases:
            with self.subTest(score=score):
                result = risk_policy(state_for(MachineType.REACTOR, score=score))
                self.assertEqual(result["risk_level"], expected)
                self.assertEqual(result["emergency_reasons"], [])

    def test_emergency_rules_override_low_ml_score(self) -> None:
        cases = (
            state_for(
                MachineType.REACTOR,
                sensor={"temperature": 42.0, "pressure": 25.0, "gas": 2.0, "sparks": 0},
            ),
            state_for(
                MachineType.COMPRESSOR,
                sensor={"vibration": 4.8, "speed": 2000.0, "pressure": 25.0},
            ),
            state_for(
                MachineType.STORAGE_TANK,
                sensor={"gas": 9.0, "sparks": 3, "pressure": 25.0},
            ),
            state_for(
                MachineType.PUMP,
                sensor={"vibration": 4.5, "pressure": 10.0},
            ),
        )
        for state in cases:
            with self.subTest(machine_type=state["machine_type"]):
                result = risk_policy(state)
                self.assertEqual(result["risk_level"], RiskLevel.EMERGENCY)
                self.assertTrue(result["emergency_reasons"])

    def test_invalid_thresholds_return_explicit_error(self) -> None:
        state = state_for(MachineType.REACTOR)
        state["prediction_thresholds"] = {"caution": 0.5, "warning": 0.2}

        result = risk_policy(state)

        self.assertEqual(result["error_code"], "RISK_POLICY_FAILED")
        self.assertEqual(result["failed_node"], "risk_policy")
        self.assertNotIn("risk_level", result)

    def test_route_labels_match_final_graph(self) -> None:
        self.assertEqual(route_by_risk({"risk_level": RiskLevel.NORMAL}), "normal")
        self.assertEqual(route_by_risk({"risk_level": RiskLevel.CAUTION}), "abnormal")
        self.assertEqual(route_by_risk({"risk_level": RiskLevel.WARNING}), "abnormal")
        self.assertEqual(route_by_risk({"risk_level": RiskLevel.EMERGENCY}), "emergency")


if __name__ == "__main__":
    unittest.main()
