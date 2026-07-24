"""Unit tests for `app.agents.predictive.predictive_agent`."""

from __future__ import annotations

import pytest

from app.agents.predictive import predictive_agent
from app.core.enums import MachineType, MeasurementMode
from app.core.exceptions import ModelArtifactError


def _base_state() -> dict:
    return {
        "sensor_reading": {
            "temperature": 30.0,
            "pressure": 2.0,
            "humidity": 40.0,
            "vibration": 0.2,
            "speed": 1000.0,
            "age": 3,
            "service_days": 120,
            "gas": 0.1,
            "sparks": 0,
            "shift": "Day",
            "experience": "Senior",
            "training": "Yes",
        },
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "measurement_mode": MeasurementMode.PERIODIC,
    }


def test_predictive_agent_returns_only_the_contracted_fields(monkeypatch):
    monkeypatch.setattr(
        "app.services.ml_service.predict_risk_score",
        lambda **kwargs: (0.42, "model-v1", {"caution": 0.145, "warning": 0.29}),
    )

    result = predictive_agent(_base_state())

    assert result == {
        "ml_risk_score": 0.42,
        "model_version": "model-v1",
        "prediction_thresholds": {"caution": 0.145, "warning": 0.29},
    }


def test_predictive_agent_propagates_model_artifact_error(monkeypatch):
    """A model-load failure must surface, never be swallowed into a fake score."""

    def _raise(**kwargs):
        raise ModelArtifactError("pipeline file missing")

    monkeypatch.setattr("app.services.ml_service.predict_risk_score", _raise)

    with pytest.raises(ModelArtifactError):
        predictive_agent(_base_state())
