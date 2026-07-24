"""Adapter around the persisted industrial-fire accident model pipeline.

Loads the two artifacts `industrial_fire_custom_accident_ml.ipynb` persists
(see CLAUDE.md): a scikit-learn `Pipeline` joblib file and a metadata JSON
file carrying `feature_columns` and the caution/warning thresholds. Neither
artifact is committed to the repo (gitignored build output) — rerun that
notebook to regenerate them before `predict_risk_score` can succeed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.core.config import settings
from app.core.enums import MachineType
from app.core.exceptions import MLServiceError, ModelArtifactError, ModelInputError
from app.models.sensor import MODEL_COLUMN_MAP


@dataclass(frozen=True)
class ModelArtifacts:
    """In-memory handle for the loaded pipeline plus the fields read from it."""

    pipeline: Any
    model_version: str
    caution_threshold: float
    warning_threshold: float
    feature_columns: list[str]


@lru_cache(maxsize=1)
def _load_artifacts() -> ModelArtifacts:
    """Load and cache the persisted model pipeline and its metadata."""

    pipeline_path = Path(settings.model_pipeline_path)
    metadata_path = Path(settings.model_metadata_path)

    if not pipeline_path.exists() or not metadata_path.exists():
        raise ModelArtifactError(
            "model artifacts not found "
            f"(pipeline={pipeline_path}, metadata={metadata_path}); rerun "
            "industrial_fire_custom_accident_ml.ipynb to regenerate them (see CLAUDE.md)"
        )

    try:
        pipeline = joblib.load(pipeline_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        raise ModelArtifactError(f"failed to load model artifacts: {exc}") from exc

    try:
        thresholds = metadata.get("thresholds", metadata)
        caution_threshold = float(thresholds["caution_threshold"])
        warning_threshold = float(thresholds["warning_threshold"])
        feature_columns = list(metadata["feature_columns"])
        model_version = str(metadata.get("model_version", pipeline_path.stem))
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelArtifactError(f"model metadata is missing a required key: {exc}") from exc

    return ModelArtifacts(
        pipeline=pipeline,
        model_version=model_version,
        caution_threshold=caution_threshold,
        warning_threshold=warning_threshold,
        feature_columns=feature_columns,
    )


def clear_artifact_cache() -> None:
    """Drop the cached model pipeline/metadata (used by tests and hot-reload)."""

    _load_artifacts.cache_clear()


def _build_feature_row(
    sensor_reading: dict[str, Any], machine_id: str, machine_type: MachineType
) -> dict[str, Any]:
    """Translate a snake_case `sensor_reading` dict into the model's training columns."""

    row: dict[str, Any] = {"machine_id": machine_id, "machine_type": str(machine_type)}
    for local_name, model_column in MODEL_COLUMN_MAP.items():
        if local_name in ("machine_id", "machine_type"):
            continue
        if local_name not in sensor_reading:
            raise ModelInputError(f"sensor_reading is missing required field '{local_name}'")
        row[model_column] = sensor_reading[local_name]
    return row


def predict_risk_score(
    sensor_reading: dict[str, Any],
    machine_id: str,
    machine_type: MachineType,
) -> tuple[float, str, dict[str, float]]:
    """Score one sensor reading.

    Returns `(ml_risk_score, model_version, {"caution": ..., "warning": ...})`.
    Raises `ModelArtifactError` if the pipeline/metadata can't be loaded,
    `ModelInputError` if `sensor_reading` can't fill the model's feature
    columns, or `MLServiceError` if inference itself fails. Never returns a
    fabricated score — a model failure must not be treated as NORMAL.
    """

    artifacts = _load_artifacts()
    row = _build_feature_row(sensor_reading, machine_id, machine_type)

    frame = pd.DataFrame([row])
    missing_columns = [c for c in artifacts.feature_columns if c not in frame.columns]
    if missing_columns:
        raise ModelInputError(f"sensor_reading cannot fill model columns: {missing_columns}")
    frame = frame[artifacts.feature_columns]

    try:
        risk_score = float(artifacts.pipeline.predict_proba(frame)[0, 1])
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed application error
        raise MLServiceError(f"model inference failed: {exc}") from exc

    thresholds = {"caution": artifacts.caution_threshold, "warning": artifacts.warning_threshold}
    return risk_score, artifacts.model_version, thresholds
