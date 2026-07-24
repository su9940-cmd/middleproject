"""Integration tests for `app.graph.builder.build_safety_graph`.

RAG/memory/action-draft/validator/notification/worker-interrupt/recheck
nodes belong to roles A/B/C and don't exist yet, so `build_safety_graph`
wires in stubs that raise `NotImplementedError` for those. The abnormal/
emergency tests below assert on that stub being reached - once a role lands
their real node, these tests should be updated to assert real behavior
instead of the stub's exception.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums import AlertStatus, MachineType, MeasurementMode, RiskLevel
from app.graph.builder import build_safety_graph

_THRESHOLDS = {"caution": 0.145, "warning": 0.29}


def _base_reading(**overrides) -> dict:
    reading = {
        "temperature": 20.0,
        "pressure": 1.0,
        "humidity": 40.0,
        "vibration": 0.1,
        "speed": 1000.0,
        "age": 2,
        "service_days": 100,
        "gas": 0.0,
        "sparks": 0,
        "shift": "Day",
        "experience": "Senior",
        "training": "Yes",
    }
    reading.update(overrides)
    return reading


def _base_state(thread_id: str, sensor_reading: dict) -> dict:
    return {
        "thread_id": thread_id,
        "reading_id": f"RD-M0101-{thread_id}",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "measured_at": datetime.now(timezone.utc),
        "measurement_mode": MeasurementMode.PERIODIC,
        "sensor_reading": sensor_reading,
        "alert_status": AlertStatus.NONE,
        "consecutive_normal_count": 0,
    }


def _invoke(graph, thread_id: str, state: dict) -> dict:
    return graph.invoke(state, config={"configurable": {"thread_id": thread_id}})


def test_build_safety_graph_compiles_with_all_ten_nodes():
    graph = build_safety_graph()
    node_names = set(graph.get_graph().nodes.keys())

    expected = {
        "predictive_agent",
        "risk_policy",
        "recovery_node",
        "rag_agent",
        "memory_agent",
        "action_draft_node",
        "validator_agent",
        "send_immediate_alert",
        "worker_interrupt",
        "request_immediate_recheck",
    }
    assert expected <= node_names


def test_predictive_agent_failure_ends_the_run_instead_of_crashing_risk_policy(monkeypatch):
    """A model-load failure must stop the run cleanly, not KeyError inside risk_policy."""

    def _raise(**kwargs):
        from app.core.exceptions import ModelArtifactError

        raise ModelArtifactError("no model artifacts on disk")

    monkeypatch.setattr("app.services.ml_service.predict_risk_score", _raise)

    graph = build_safety_graph()
    state = _base_state("M-0101:predictive-failure-case", _base_reading())
    result = _invoke(graph, "M-0101:predictive-failure-case", state)

    assert result["error_code"] == "MODEL_LOAD_FAILED"
    assert result["failed_node"] == "predictive_agent"
    assert "risk_level" not in result


def test_normal_reading_reaches_recovery_node_and_ends(monkeypatch):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    graph = build_safety_graph()
    state = _base_state("M-0101:normal-case", _base_reading())
    result = _invoke(graph, "M-0101:normal-case", state)

    assert result["risk_level"] == RiskLevel.NORMAL
    assert result["alert_status"] == AlertStatus.NONE
    assert result["consecutive_normal_count"] == 0


def test_abnormal_reading_fans_out_to_rag_and_memory(monkeypatch):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.5, "test-v1", _THRESHOLDS),
    )

    graph = build_safety_graph()
    state = _base_state("M-0101:warning-case", _base_reading())

    with pytest.raises(NotImplementedError, match="rag_agent|memory_agent"):
        _invoke(graph, "M-0101:warning-case", state)


def test_abnormal_reading_opens_the_alert_before_hitting_the_rag_memory_stub(monkeypatch):
    """alert_lifecycle_node must run (and be checkpointed) even though the run fails later."""

    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.5, "test-v1", _THRESHOLDS),
    )

    graph = build_safety_graph()
    thread_id = "M-0101:alert-lifecycle-case"
    state = _base_state(thread_id, _base_reading())

    with pytest.raises(NotImplementedError):
        _invoke(graph, thread_id, state)

    checkpointed = graph.get_state(config={"configurable": {"thread_id": thread_id}})
    assert checkpointed.values["alert_status"] == AlertStatus.OPEN
    assert checkpointed.values["repeat_count"] == 0


def test_emergency_reading_also_fans_out_to_immediate_alert(monkeypatch):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.01, "test-v1", _THRESHOLDS),
    )

    graph = build_safety_graph()
    # REACTOR emergency rule: temperature >= 42.
    state = _base_state("M-0101:emergency-case", _base_reading(temperature=50.0))

    with pytest.raises(NotImplementedError, match="rag_agent|memory_agent|send_immediate_alert"):
        _invoke(graph, "M-0101:emergency-case", state)
