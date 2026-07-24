"""Runtime configuration sourced from environment variables (no hardcoded secrets/paths)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Process-wide settings resolved once at import time."""

    model_pipeline_path: str
    model_metadata_path: str
    policy_version: str
    database_url: str


def _load_settings() -> Settings:
    return Settings(
        model_pipeline_path=os.environ.get(
            "MODEL_PIPELINE_PATH", "models/industrial_fire_accident_pipeline.joblib"
        ),
        model_metadata_path=os.environ.get(
            "MODEL_METADATA_PATH", "models/industrial_fire_accident_metadata.json"
        ),
        policy_version=os.environ.get("RISK_POLICY_VERSION", "risk-policy-v1"),
        database_url=os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./safety_app.db"),
    )


settings = _load_settings()
