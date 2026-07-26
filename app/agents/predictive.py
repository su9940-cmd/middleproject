"""Predictive Agent node for LangGraph."""

from functools import lru_cache
from typing import Any

from app.core.exceptions import MLServiceError, ModelInputError
from app.graph.state import SafetyState
from app.services import ml_service
from app.services.ml_service import MLService


@lru_cache(maxsize=1)
def get_ml_service() -> MLService:
    """Return the process-wide cached ML service."""

    return MLService()


def predictive_agent(state: SafetyState) -> dict[str, Any]:
    """Calculate an ML risk score and return only changed state fields."""

    reading = state.get("sensor_reading")
    if reading is None:
        return {
            "error_code": ModelInputError.error_code,
            "error_message": "sensor_reading is required",
            "failed_node": "predictive_agent",
        }

    payload = dict(reading)
    for key in (
        "reading_id",
        "machine_id",
        "machine_type",
        "measured_at",
        "measurement_mode",
    ):
        if key not in payload and key in state:
            payload[key] = state[key]

    try:
        score, model_version, prediction_thresholds = ml_service.predict_risk_score(
            sensor_reading=payload,
            machine_id=str(state.get("machine_id") or payload.get("machine_id") or ""),
            machine_type=state.get("machine_type") or payload.get("machine_type"),
        )
    except MLServiceError as exc:
        return {
            "error_code": exc.error_code,
            "error_message": str(exc),
            "failed_node": "predictive_agent",
        }

    return {
        "ml_risk_score": score,
        "model_version": model_version,
        "prediction_thresholds": prediction_thresholds,
        "error_code": None,
        "error_message": None,
        "failed_node": None,
    }
