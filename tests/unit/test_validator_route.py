"""Validator routing guard tests."""

import unittest

from app.graph.builder import (
    MAX_VALIDATION_ATTEMPTS,
    _checklist_validation_failure,
    _route_after_validator,
)


class ValidatorRouteTest(unittest.TestCase):
    def test_passed_and_legacy_final_checklist_continue(self) -> None:
        self.assertEqual(_route_after_validator({"validation_status": "PASSED"}), "passed")
        self.assertEqual(_route_after_validator({"final_checklist": {"items": []}}), "passed")

    def test_revision_routes_back_below_limit(self) -> None:
        self.assertEqual(
            _route_after_validator(
                {"validation_status": "REVISE", "validation_attempts": 1}
            ),
            "revise",
        )

    def test_revision_stops_at_limit(self) -> None:
        self.assertEqual(
            _route_after_validator(
                {
                    "validation_status": "REVISE",
                    "validation_attempts": MAX_VALIDATION_ATTEMPTS,
                }
            ),
            "error",
        )

    def test_retry_exhaustion_records_stable_error_contract(self) -> None:
        result = _checklist_validation_failure(
            {"validation_attempts": MAX_VALIDATION_ATTEMPTS}
        )
        self.assertEqual(result["error_code"], "CHECKLIST_VALIDATION_FAILED")
        self.assertEqual(result["failed_node"], "validator_agent")


if __name__ == "__main__":
    unittest.main()
