"""Predictive Agent — scores the current sensor reading with the persisted ML pipeline."""

from __future__ import annotations

from typing import Any

from app.graph.state import SafetyState
from app.services import ml_service


def predictive_agent(state: SafetyState) -> dict[str, Any]:
    """Score `state["sensor_reading"]` and report the ML risk probability.

    Reads `sensor_reading`, `machine_id`, `machine_type` from `state`.
    Raises `ModelArtifactError` / `ModelInputError` / `MLServiceError` (see
    `app.core.exceptions`) on failure instead of returning a fabricated
    score — a model failure must never be treated as NORMAL.
    """

    ml_risk_score, model_version, prediction_thresholds = ml_service.predict_risk_score(
        sensor_reading=state["sensor_reading"],
        machine_id=state["machine_id"],
        machine_type=state["machine_type"],
    )

    return {
        "ml_risk_score": ml_risk_score,
        "model_version": model_version,
        "prediction_thresholds": prediction_thresholds,
    }
