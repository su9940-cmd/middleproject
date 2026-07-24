"""Integration tests for `/maintenance-requests` (FR-14): HTTP round trip + camelCase contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.enums import MachineType
from app.repositories.maintenance_repository import MaintenanceRequestRepository


@pytest.fixture
def client():
    """Fresh in-memory DB per test."""

    db.configure("sqlite+aiosqlite:///:memory:")
    import main

    with TestClient(main.app) as test_client:
        yield test_client


async def _seed_draft(**overrides) -> None:
    data = {
        "maintenance_request_id": "MR-AL-M0101-001",
        "alert_id": "AL-M0101-001",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "title": "가스 감지 센서 및 안전밸브 정밀 점검",
        "recommendation": "가스 감지 센서 교정 상태를 재점검할 것을 권장합니다.",
        "priority": "높음",
    }
    data.update(overrides)
    async with db.session_scope() as session:
        await MaintenanceRequestRepository(session).create_draft(data)


def test_list_pending_returns_camel_case_fields(client):
    import asyncio

    asyncio.run(_seed_draft())

    resp = client.get("/maintenance-requests/pending")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    item = body[0]
    # camelCase on the wire, per the 2026-07-24 team convention.
    assert item["maintenanceRequestId"] == "MR-AL-M0101-001"
    assert item["alertId"] == "AL-M0101-001"
    assert item["machineId"] == "M-0101"
    assert item["machineType"] == "REACTOR"
    assert item["status"] == "PENDING"
    assert "decidedAt" in item
    assert "maintenance_request_id" not in item


def test_list_pending_excludes_already_decided(client):
    import asyncio

    asyncio.run(_seed_draft())
    client.post(
        "/maintenance-requests/MR-AL-M0101-001/decision",
        json={"maintenanceDecision": "APPROVED", "decidedBy": "manager-1", "comment": "승인"},
    )

    resp = client.get("/maintenance-requests/pending")

    assert resp.status_code == 200
    assert resp.json() == []


def test_decide_approves_a_pending_request(client):
    import asyncio

    asyncio.run(_seed_draft())

    resp = client.post(
        "/maintenance-requests/MR-AL-M0101-001/decision",
        json={"maintenanceDecision": "APPROVED", "decidedBy": "manager-1", "comment": "승인"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "APPROVED"
    assert body["decidedBy"] == "manager-1"
    assert body["decisionComment"] == "승인"
    assert body["decidedAt"] is not None


def test_decide_rejects_when_already_decided(client):
    import asyncio

    asyncio.run(_seed_draft())
    client.post(
        "/maintenance-requests/MR-AL-M0101-001/decision",
        json={"maintenanceDecision": "APPROVED"},
    )

    resp = client.post(
        "/maintenance-requests/MR-AL-M0101-001/decision",
        json={"maintenanceDecision": "REJECTED"},
    )

    assert resp.status_code == 409


def test_decide_unknown_request_is_a_404(client):
    resp = client.post(
        "/maintenance-requests/MR-does-not-exist/decision",
        json={"maintenanceDecision": "APPROVED"},
    )

    assert resp.status_code == 404


def test_decide_rejects_invalid_decision_value(client):
    import asyncio

    asyncio.run(_seed_draft())

    resp = client.post(
        "/maintenance-requests/MR-AL-M0101-001/decision",
        json={"maintenanceDecision": "PENDING"},
    )

    assert resp.status_code == 422
