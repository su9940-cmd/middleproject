"""Unit tests for `app.services.iot_service.request_measurement`."""

from __future__ import annotations

import pytest

from app.core.exceptions import RecheckRequestError
from app.services.iot_service import request_measurement


def test_request_measurement_succeeds_for_a_valid_machine_id():
    request_measurement(machine_id="M-0101", reason="immediate_recheck")


def test_request_measurement_rejects_an_empty_machine_id():
    with pytest.raises(RecheckRequestError):
        request_measurement(machine_id="", reason="immediate_recheck")
