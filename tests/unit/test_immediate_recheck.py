"""Unit tests for `app.nodes.immediate_recheck.request_immediate_recheck`."""

from __future__ import annotations

from datetime import datetime

from app.core.enums import AlertStatus
from app.nodes.immediate_recheck import request_immediate_recheck


def test_request_immediate_recheck_marks_waiting_recheck():
    result = request_immediate_recheck({"alert_id": "AL-M0101-20260723T101500"})

    assert result["alert_status"] == AlertStatus.WAITING_RECHECK
    assert isinstance(result["recheck_requested_at"], datetime)
