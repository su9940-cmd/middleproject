"""Tests for consecutive-normal recovery transitions."""

import unittest

from app.core.enums import AlertStatus, MeasurementMode, RiskLevel
from app.nodes.recovery import recovery_node


class RecoveryNodeTest(unittest.TestCase):
    """Verify the two-normal-reading resolution policy."""

    def test_normal_without_open_alert_ends_silently(self) -> None:
        result = recovery_node(
            {
                "risk_level": RiskLevel.NORMAL,
                "measurement_mode": MeasurementMode.PERIODIC,
                "alert_status": AlertStatus.NONE,
                "consecutive_normal_count": 0,
            }
        )

        self.assertEqual(result["alert_status"], AlertStatus.NONE)
        self.assertEqual(result["consecutive_normal_count"], 0)

    def test_immediate_normal_starts_monitoring(self) -> None:
        result = recovery_node(
            {
                "risk_level": RiskLevel.NORMAL,
                "measurement_mode": MeasurementMode.IMMEDIATE_RECHECK,
                "alert_status": AlertStatus.WAITING_RECHECK,
                "consecutive_normal_count": 0,
            }
        )

        self.assertEqual(result["alert_status"], AlertStatus.MONITORING)
        self.assertEqual(result["consecutive_normal_count"], 1)

    def test_next_periodic_normal_resolves_alert(self) -> None:
        result = recovery_node(
            {
                "risk_level": RiskLevel.NORMAL,
                "measurement_mode": MeasurementMode.PERIODIC,
                "alert_status": AlertStatus.MONITORING,
                "consecutive_normal_count": 1,
            }
        )

        self.assertEqual(result["alert_status"], AlertStatus.RESOLVED)
        self.assertEqual(result["consecutive_normal_count"], 2)

    def test_periodic_normal_for_open_alert_starts_monitoring(self) -> None:
        result = recovery_node(
            {
                "risk_level": RiskLevel.NORMAL,
                "measurement_mode": MeasurementMode.PERIODIC,
                "alert_status": AlertStatus.OPEN,
                "consecutive_normal_count": 0,
            }
        )

        self.assertEqual(result["alert_status"], AlertStatus.MONITORING)
        self.assertEqual(result["consecutive_normal_count"], 1)

    def test_non_normal_input_is_rejected(self) -> None:
        result = recovery_node({"risk_level": RiskLevel.WARNING})

        self.assertEqual(result["error_code"], "RECOVERY_STATE_FAILED")
        self.assertEqual(result["failed_node"], "recovery_node")


if __name__ == "__main__":
    unittest.main()
