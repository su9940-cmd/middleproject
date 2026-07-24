"""Unit tests for `app.nodes.worker_interrupt.worker_interrupt`.

Exercised through a small standalone graph (not `build_safety_graph`) since
`interrupt`/resume semantics require a compiled, checkpointed graph to
observe - see `langgraph.types.interrupt`.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from app.core.enums import MachineType, NotificationStatus, RiskLevel
from app.graph.state import SafetyState
from app.nodes.worker_interrupt import worker_interrupt


def _build_graph():
    graph = StateGraph(SafetyState)
    graph.add_node("worker_interrupt", worker_interrupt)
    graph.set_entry_point("worker_interrupt")
    graph.add_edge("worker_interrupt", END)
    return graph.compile(checkpointer=InMemorySaver())


def _incident_state(**overrides) -> dict[str, Any]:
    state: dict[str, Any] = {
        "alert_id": "AL-M0101-20260723T101500",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "measured_at": "2026-07-23T10:15:00+00:00",
        "risk_level": RiskLevel.EMERGENCY,
        "ml_risk_score": 0.91,
        "emergency_reasons": ["REACTOR: temperature 50.0 >= 42"],
        "final_checklist": {"checklist_id": "CL-AL-M0101-20260723T101500-V1", "items": []},
        "notification_status": NotificationStatus.SENT,
        "immediate_alert_sent_at": "2026-07-23T10:15:01+00:00",
    }
    state.update(overrides)
    return state


def test_worker_interrupt_pauses_and_surfaces_the_incident_context():
    """Payload must match `WorkerInterruptScreen`'s props field-for-field (role E)."""

    graph = _build_graph()
    config = {"configurable": {"thread_id": "M-0101:AL-M0101-20260723T101500"}}

    result = graph.invoke(_incident_state(), config=config)

    assert "__interrupt__" in result
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["alert_id"] == "AL-M0101-20260723T101500"
    assert interrupt_payload["machine_id"] == "M-0101"
    assert interrupt_payload["machine_type"] == MachineType.REACTOR
    assert interrupt_payload["risk_level"] == RiskLevel.EMERGENCY
    assert interrupt_payload["ml_risk_score"] == 0.91
    assert interrupt_payload["emergency_reasons"] == ["REACTOR: temperature 50.0 >= 42"]
    assert interrupt_payload["final_checklist"]["checklist_id"] == "CL-AL-M0101-20260723T101500-V1"
    assert interrupt_payload["notification_status"] == NotificationStatus.SENT
    assert interrupt_payload["immediate_alert_sent_at"] == "2026-07-23T10:15:01+00:00"


def test_worker_interrupt_resumes_with_the_submitted_response():
    graph = _build_graph()
    config = {"configurable": {"thread_id": "M-0101:AL-M0101-resume-case"}}
    state = _incident_state(
        alert_id="AL-M0101-resume-case",
        final_checklist={"checklist_id": "CL-AL-M0101-resume-case-V1", "items": []},
    )
    graph.invoke(state, config=config)

    # This is exactly what `WorkerInterruptScreen.handleSubmit` (role E) sends.
    worker_response = {
        "response_id": "RP-AL-M0101-resume-case-1721728800000",
        "alert_id": "AL-M0101-resume-case",
        "submitted_at": "2026-07-23T10:20:00.000Z",
        "item_statuses": {"CI-1": "COMPLETED"},
        "note": "밸브 조치 완료",
    }
    result = graph.invoke(Command(resume=worker_response), config=config)

    assert "__interrupt__" not in result
    assert result["worker_response"] == worker_response
