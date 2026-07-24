"""Unit tests for `app.nodes.immediate_recheck.request_immediate_recheck`.

`app.nodes.immediate_recheck` does `from app.services.iot_service import
request_measurement`, binding the name locally - so these tests patch
`app.nodes.immediate_recheck.request_measurement`.
"""

from __future__ import annotations

from datetime import datetime

from app.core.enums import AlertStatus
from app.core.exceptions import RecheckRequestError
from app.nodes.immediate_recheck import request_immediate_recheck


def test_request_immediate_recheck_marks_waiting_recheck(monkeypatch):
    monkeypatch.setattr(
        "app.nodes.immediate_recheck.request_measurement",
        lambda machine_id, reason: None,
    )

    result = request_immediate_recheck({"machine_id": "M-0101"})

    assert result["alert_status"] == AlertStatus.WAITING_RECHECK
    assert isinstance(result["recheck_requested_at"], datetime)


def test_request_immediate_recheck_reports_error_fields_on_recheck_request_error(monkeypatch):
    def _raise(machine_id: str, reason: str) -> None:
        raise RecheckRequestError("device unreachable")

    monkeypatch.setattr("app.nodes.immediate_recheck.request_measurement", _raise)

    result = request_immediate_recheck({"machine_id": "M-0101"})

    assert result == {
        "error_code": "RECHECK_REQUEST_FAILED",
        "error_message": "device unreachable",
        "failed_node": "request_immediate_recheck",
    }


def test_request_immediate_recheck_reports_error_fields_on_unexpected_exception(monkeypatch):
    def _raise(machine_id: str, reason: str) -> None:
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.nodes.immediate_recheck.request_measurement", _raise)

    result = request_immediate_recheck({"machine_id": "M-0101"})

    assert result["error_code"] == "RECHECK_REQUEST_FAILED"
    assert result["failed_node"] == "request_immediate_recheck"
    assert "timeout" in result["error_message"]
