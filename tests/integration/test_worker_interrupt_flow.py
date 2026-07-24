"""End-to-end test of the abnormal/emergency closed loop through the real HTTP API:

`POST /sensors/ingest` (EMERGENCY reading) -> graph fans out to
`send_immediate_alert` + `rag_agent`/`memory_agent` -> `action_draft_node` ->
`validator_agent` -> `worker_interrupt` pauses -> `POST
/worker/checklists/{id}/respond` resumes it -> `request_immediate_recheck` ->
END.

`rag_agent`/`memory_agent`/`action_draft_node`/`validator_agent` are owned by
roles A/B and don't exist in this repo yet, so this test stands minimal fakes
in for them (installed into `sys.modules` before the graph is built) purely
to exercise the role C slice end to end: notification dispatch, checklist
persistence, the worker-interrupt pause, and the resume/recheck hand-off.
"""

from __future__ import annotations

import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.enums import AlertStatus, NotificationStatus, RiskLevel
from app.repositories.alert_repository import AlertRepository

_THRESHOLDS = {"caution": 0.145, "warning": 0.29}


def _install_fake_downstream_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for roles A/B's nodes so the graph can run past `alert_lifecycle_node`."""

    rag_module = types.ModuleType("app.agents.rag")
    rag_module.rag_agent = lambda state: {  # type: ignore[attr-defined]
        "retrieved_documents": [
            {
                "source_id": "SOP-REACTOR-01",
                "document_type": "SOP",
                "title": "반응기 고온 대응 절차",
                "section": "3.2",
                "content": "온도 42도 이상 시 즉시 냉각수 밸브를 개방한다.",
                "relevance_score": 0.92,
                "manual_version": "v1",
            }
        ]
    }

    memory_module = types.ModuleType("app.agents.memory")
    memory_module.memory_agent = lambda state: {  # type: ignore[attr-defined]
        "memory_context": {
            "previous_alert_count": 0,
            "unresolved_count": 0,
            "previous_risk_level": None,
            "previous_checklist_items": [],
            "completed_action_ids": [],
            "failed_action_ids": [],
            "latest_worker_note": None,
            "maintenance_history": [],
            "is_risk_escalated": False,
            "is_repeat_limit_exceeded": False,
        }
    }

    action_draft_module = types.ModuleType("app.nodes.action_draft")

    def _action_draft_node(state: dict) -> dict:
        return {
            "action_draft": {
                "action_phase": "EMERGENCY",
                "summary": "반응기 긴급 냉각 조치",
                "action_items": [
                    {
                        "action_id": "ACT-1",
                        "title": "냉각수 밸브 개방",
                        "description": "SOP-REACTOR-01 3.2절에 따라 냉각수 밸브를 즉시 개방한다.",
                        "priority": 1,
                        "source_ids": ["SOP-REACTOR-01"],
                    }
                ],
                "requires_manager_report": True,
                "requires_maintenance_request": False,
            },
            "requires_maintenance_request": False,
        }

    action_draft_module.action_draft_node = _action_draft_node  # type: ignore[attr-defined]

    validator_module = types.ModuleType("app.agents.validator")

    def _validator_agent(state: dict) -> dict:
        alert_id = state["alert_id"]
        return {
            "final_checklist": {
                "checklist_id": f"CL-{alert_id}-V1",
                "alert_id": alert_id,
                "version": 1,
                "risk_level": state["risk_level"],
                "action_phase": "EMERGENCY",
                "items": [
                    {
                        "checklist_item_id": "CI-1",
                        "action_id": "ACT-1",
                        "title": "냉각수 밸브 개방",
                        "instruction": "SOP-REACTOR-01 3.2절에 따라 냉각수 밸브를 즉시 개방한다.",
                        "priority": 1,
                        "source_ids": ["SOP-REACTOR-01"],
                        "status": "PENDING",
                        "worker_note": None,
                        "completed_at": None,
                    }
                ],
                "requires_manager_report": True,
                "requires_maintenance_request": False,
            }
        }

    validator_module.validator_agent = _validator_agent  # type: ignore[attr-defined]

    for name, module in {
        "app.agents.rag": rag_module,
        "app.agents.memory": memory_module,
        "app.nodes.action_draft": action_draft_module,
        "app.agents.validator": validator_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """Fresh in-memory DB + a freshly-built graph with A/B's nodes faked in."""

    _install_fake_downstream_agents(monkeypatch)
    db.configure("sqlite+aiosqlite:///:memory:")
    import main

    with TestClient(main.app) as test_client:
        yield test_client


def _alert_id_from_checklist_id(checklist_id: str) -> str:
    """Reverse `CL-{alert_id}-V{version}` (see `app.core.ids`) back to `alert_id`."""

    return checklist_id.removeprefix("CL-").rsplit("-V", 1)[0]


def _payload(**overrides) -> dict:
    payload = {
        "reading_id": "RD-M0101-emergency1",
        "machine_id": "M-0101",
        "machine_type": "REACTOR",
        "measured_at": "2026-07-24T00:00:00Z",
        "measurement_mode": "PERIODIC",
        "temperature": 50.0,  # REACTOR emergency rule: temperature >= 42
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


def test_emergency_reading_pauses_at_worker_interrupt_with_checklist_saved(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    resp = client.post("/sensors/ingest", json=_payload())
    assert resp.status_code == 201
    body = resp.json()

    assert body["risk_level"] == RiskLevel.EMERGENCY
    assert body["alert_status"] == AlertStatus.ESCALATED
    assert body["awaiting_worker_response"] is True
    checklist_id = body["checklist_id"]
    assert checklist_id

    checklist_resp = client.get(f"/alerts/{_alert_id_from_checklist_id(checklist_id)}/checklist")
    assert checklist_resp.status_code == 200
    assert checklist_resp.json()["checklist_id"] == checklist_id


def test_worker_response_resumes_the_graph_and_requests_a_recheck(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    ingest_resp = client.post("/sensors/ingest", json=_payload())
    checklist_id = ingest_resp.json()["checklist_id"]

    respond_resp = client.post(
        f"/worker/checklists/{checklist_id}/respond",
        json={
            "items": [{"checklist_item_id": "CI-1", "status": "COMPLETED"}],
            "worker_note": "냉각수 밸브 개방 완료",
        },
    )

    assert respond_resp.status_code == 200
    body = respond_resp.json()
    assert body["alert_status"] == AlertStatus.WAITING_RECHECK
    assert body["recheck_requested_at"] is not None

    async def _read_alert() -> None:
        async with db.session_scope() as session:
            alert_id = _alert_id_from_checklist_id(checklist_id)
            alert = await AlertRepository(session).get_by_id(alert_id)
            assert alert is not None
            assert alert.alert_status == AlertStatus.WAITING_RECHECK
            assert alert.notification_status == NotificationStatus.SENT

    import asyncio

    asyncio.run(_read_alert())


def test_responding_to_a_non_pending_checklist_is_rejected(monkeypatch, client):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    ingest_resp = client.post("/sensors/ingest", json=_payload())
    checklist_id = ingest_resp.json()["checklist_id"]

    first = client.post(f"/worker/checklists/{checklist_id}/respond", json={"items": []})
    assert first.status_code == 200

    second = client.post(f"/worker/checklists/{checklist_id}/respond", json={"items": []})
    assert second.status_code == 409


def test_responding_to_an_unknown_checklist_is_a_404(client):
    resp = client.post("/worker/checklists/CL-does-not-exist-V1/respond", json={"items": []})
    assert resp.status_code == 404
