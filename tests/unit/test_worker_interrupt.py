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

from app.graph.state import SafetyState
from app.nodes.worker_interrupt import worker_interrupt


def _build_graph():
    graph = StateGraph(SafetyState)
    graph.add_node("worker_interrupt", worker_interrupt)
    graph.set_entry_point("worker_interrupt")
    graph.add_edge("worker_interrupt", END)
    return graph.compile(checkpointer=InMemorySaver())


def test_worker_interrupt_pauses_and_surfaces_the_checklist():
    graph = _build_graph()
    config = {"configurable": {"thread_id": "M-0101:AL-M0101-20260723T101500"}}
    state: dict[str, Any] = {
        "alert_id": "AL-M0101-20260723T101500",
        "final_checklist": {"checklist_id": "CL-AL-M0101-20260723T101500-V1", "items": []},
    }

    result = graph.invoke(state, config=config)

    assert "__interrupt__" in result
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["alert_id"] == "AL-M0101-20260723T101500"
    assert interrupt_payload["checklist_id"] == "CL-AL-M0101-20260723T101500-V1"


def test_worker_interrupt_resumes_with_the_submitted_response():
    graph = _build_graph()
    config = {"configurable": {"thread_id": "M-0101:AL-M0101-resume-case"}}
    state: dict[str, Any] = {
        "alert_id": "AL-M0101-resume-case",
        "final_checklist": {"checklist_id": "CL-AL-M0101-resume-case-V1", "items": []},
    }
    graph.invoke(state, config=config)

    worker_response = {
        "checklist_id": "CL-AL-M0101-resume-case-V1",
        "items": [{"checklist_item_id": "CI-1", "status": "COMPLETED"}],
        "worker_note": "밸브 조치 완료",
    }
    result = graph.invoke(Command(resume=worker_response), config=config)

    assert "__interrupt__" not in result
    assert result["worker_response"] == worker_response
