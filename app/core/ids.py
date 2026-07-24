"""ID generation helpers matching the shared ID-format contract (section 10)."""

from __future__ import annotations

from datetime import datetime


def _timestamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def generate_reading_id(machine_id: str, measured_at: datetime) -> str:
    """RD-{machine_id_no_hyphen}-{timestamp}, e.g. RD-M0101-20260723T101500."""

    return f"RD-{machine_id.replace('-', '')}-{_timestamp(measured_at)}"


def generate_alert_id(machine_id: str, opened_at: datetime) -> str:
    """AL-{machine_id_no_hyphen}-{timestamp}, e.g. AL-M0101-20260723T101500."""

    return f"AL-{machine_id.replace('-', '')}-{_timestamp(opened_at)}"


def build_thread_id(machine_id: str, alert_id: str) -> str:
    """{machine_id}:{alert_id} - machine_id keeps its hyphen here (":" is the delimiter)."""

    return f"{machine_id}:{alert_id}"
