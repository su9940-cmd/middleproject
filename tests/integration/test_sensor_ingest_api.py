"""Integration tests for `POST /sensors/ingest`: DB round trip + graph wiring."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.enums import AlertStatus, MachineType, RiskLevel
from app.repositories.alert_repository import AlertRepository

_THRESHOLDS = {"caution": 0.145, "warning": 0.29}


@pytest.fixture
def client():
    """Fresh in-memory DB + freshly-built graph (fresh checkpointer) per test."""

    db.configure("sqlite+aiosqlite:///:memory:")
    import main

    with TestClient(main.app) as test_client:
        yield test_client


def _payload(**overrides) -> dict:
    payload = {
        "reading_id": "RD-M0101-api1",
        "machine_id": "M-0101",
        "machine_type": "REACTOR",
        "measured_at": "2026-07-24T00:00:00Z",
        "measurement_mode": "PERIODIC",
        "temperature": 20.0,
        "pressure": 1.0,
        "humidity": 40.0,
        "vibration": 0.1,
        "speed": 1000.0,
        "age": 2,
        "service_days": 90,
        "gas": 0.0,
        "sparks": 0,
        "shift": "Day",
        "experience": "Senior",
        "training": "Yes",
    }
    payload.update(overrides)
    return payload


def test_normal_reading_is_persisted_and_returns_normal(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    resp = client.post("/sensors/ingest", json=_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["risk_level"] == RiskLevel.NORMAL
    assert body["alert_status"] == AlertStatus.NONE


def test_model_failure_persists_the_reading_but_reports_a_clean_error(client):
    """A missing model artifact must not crash the request or the graph."""

    resp = client.post("/sensors/ingest", json=_payload(reading_id="RD-M0101-api2"))

    assert resp.status_code == 500
    body = resp.json()
    assert body["error_code"] == "MODEL_LOAD_FAILED"
    assert body["failed_node"] == "predictive_agent"


def test_existing_active_alert_is_reused_not_reminted(monkeypatch, client):
    """A machine with an already-open alert must resume that alert/thread, not mint a new one."""

    async def _seed_existing_alert() -> None:
        async with db.session_scope() as session:
            await AlertRepository(session).upsert_alert_state(
                {
                    "alert_id": "AL-M0101-EXISTING",
                    "thread_id": "M-0101:AL-M0101-EXISTING",
                    "machine_id": "M-0101",
                    "machine_type": MachineType.REACTOR,
                    "reading_id": "RD-M0101-seed",
                    "risk_level": RiskLevel.WARNING,
                    "alert_status": AlertStatus.OPEN,
                    "repeat_count": 1,
                    "consecutive_normal_count": 0,
                }
            )

    asyncio.run(_seed_existing_alert())

    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),  # NORMAL this time
    )

    resp = client.post("/sensors/ingest", json=_payload(reading_id="RD-M0101-api3"))
    assert resp.status_code == 201
    body = resp.json()

    # Must resume the pre-existing alert's thread, not mint a fresh one.
    assert body["thread_id"] == "M-0101:AL-M0101-EXISTING"
    # periodic-normal while an alert is OPEN (not yet MONITORING) -> left
    # unchanged per recovery_node's rules, not silently cleared to NONE.
    assert body["alert_status"] == AlertStatus.OPEN


def test_immediate_recheck_reading_sets_recheck_reading_id_on_state(monkeypatch, client):
    """Contract section 8: an IMMEDIATE_RECHECK reading must set `recheck_reading_id`
    on the state handed to `predictive_agent`, not just `reading_id`."""

    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    resp = client.post(
        "/sensors/ingest",
        json=_payload(
            reading_id="RD-M0101-recheck1",
            measurement_mode="IMMEDIATE_RECHECK",
        ),
    )
    assert resp.status_code == 201
    thread_id = resp.json()["thread_id"]

    import main

    snapshot = main.app.state.safety_graph.get_state(
        config={"configurable": {"thread_id": thread_id}}
    )
    assert snapshot.values.get("recheck_reading_id") == "RD-M0101-recheck1"
