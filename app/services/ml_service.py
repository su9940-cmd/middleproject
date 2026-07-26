"""Loading and inference adapter for the trained accident-risk pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import pandas as pd

from app.core.exceptions import ModelArtifactError, ModelInputError, MLServiceError
from app.models.sensor import SensorReading


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "industrial_fire_accident_pipeline.joblib"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "models" / "industrial_fire_accident_metadata.json"

MODEL_COLUMN_MAP = {
    "temperature": "Temp",
    "pressure": "Pressure",
    "humidity": "Humidity",
    "vibration": "Vibration",
    "speed": "Speed",
    "age": "Age",
    "service_days": "Service_Days",
    "gas": "Gas",
    "sparks": "Sparks",
    "shift": "Shift",
    "experience": "Exp",
    "training": "Training",
    "machine_id": "machine_id",
    "machine_type": "machine_type",
}


@dataclass(frozen=True, slots=True)
class MLPrediction:
    """Stable inference result consumed by the Predictive Agent."""

    ml_risk_score: float
    model_version: str
    prediction_thresholds: dict[str, float]


class MLService:
    """Load the persisted sklearn pipeline and perform validated inference."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        metadata_path: Path | str = DEFAULT_METADATA_PATH,
    ) -> None:
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        self._model: Any | None = None
        self._metadata: dict[str, Any] | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        """Return model metadata, loading it once on first access."""

        self._ensure_loaded()
        assert self._metadata is not None
        return self._metadata

    def predict(self, reading: SensorReading | Mapping[str, Any]) -> MLPrediction:
        """Predict the positive-class ML risk score for one sensor reading."""

        self._ensure_loaded()
        assert self._model is not None
        assert self._metadata is not None

        validated = self._validate_reading(reading)
        frame = self._to_model_frame(validated)

        try:
            probabilities = self._model.predict_proba(frame)
            classes = list(self._model.classes_)
            positive_index = classes.index(1)
            score = float(probabilities[0, positive_index])
        except Exception as exc:
            raise MLServiceError(f"model inference failed: {exc}") from exc

        model_version = str(
            self._metadata.get("model_version")
            or f"{self._metadata.get('model_name', 'model')}-rs{self._metadata.get('random_state', 'unknown')}"
        )
        return MLPrediction(
            ml_risk_score=score,
            model_version=model_version,
            prediction_thresholds={
                "caution": float(self._metadata["caution_threshold"]),
                "warning": float(self._metadata["warning_threshold"]),
            },
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._metadata is not None:
            return

        if not self.model_path.is_file():
            raise ModelArtifactError(f"model file not found: {self.model_path}")
        if not self.metadata_path.is_file():
            raise ModelArtifactError(f"metadata file not found: {self.metadata_path}")

        try:
            with self.metadata_path.open("r", encoding="utf-8") as file:
                metadata = json.load(file)
            model = joblib.load(self.model_path)
        except Exception as exc:
            raise ModelArtifactError(f"failed to load model artifacts: {exc}") from exc

        required_metadata = {
            "feature_columns",
            "caution_threshold",
            "warning_threshold",
        }
        missing_metadata = sorted(required_metadata - metadata.keys())
        if missing_metadata:
            raise ModelArtifactError(
                f"metadata is missing required keys: {', '.join(missing_metadata)}"
            )
        if not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
            raise ModelArtifactError("loaded model does not support probability prediction")

        self._metadata = metadata
        self._model = model

    @staticmethod
    def _validate_reading(reading: SensorReading | Mapping[str, Any]) -> SensorReading:
        if isinstance(reading, SensorReading):
            return reading
        try:
            return SensorReading.model_validate(dict(reading))
        except Exception as exc:
            raise ModelInputError(f"invalid sensor reading: {exc}") from exc

    def _to_model_frame(self, reading: SensorReading) -> pd.DataFrame:
        source = reading.model_dump(mode="json")
        model_row = {
            model_name: source[api_name]
            for api_name, model_name in MODEL_COLUMN_MAP.items()
        }
        expected_columns = list(self.metadata["feature_columns"])
        missing_columns = [name for name in expected_columns if name not in model_row]
        if missing_columns:
            raise ModelInputError(
                f"model input mapping is missing columns: {', '.join(missing_columns)}"
            )
        return pd.DataFrame([model_row], columns=expected_columns)


def predict_risk_score(
    *,
    sensor_reading: Mapping[str, Any],
    machine_id: str,
    machine_type: Any,
) -> tuple[float, str, dict[str, float]]:
    """Compatibility adapter for the graph-level ML contract.

    The backend/API slice historically patched this function directly while
    the ML Agent used ``MLService.predict``.  Keeping this small adapter lets
    both contracts share the same persisted pipeline and makes integration
    tests able to replace inference without touching the Agent.
    """

    payload = dict(sensor_reading)
    payload.setdefault("machine_id", machine_id)
    payload.setdefault("machine_type", machine_type)
    prediction = MLService().predict(payload)
    return (
        prediction.ml_risk_score,
        prediction.model_version,
        prediction.prediction_thresholds,
    )
