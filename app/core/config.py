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
    rag_embedding_model: str
    rag_chroma_path: str
    rag_chroma_collection_name: str
    rag_default_top_k: int


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
        rag_embedding_model=os.environ.get(
            "RAG_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask"
        ),
        rag_chroma_path=os.environ.get("RAG_CHROMA_PATH", "chroma_db"),
        rag_chroma_collection_name=os.environ.get(
            "RAG_CHROMA_COLLECTION_NAME", "safety_documents__section"
        ),
        rag_default_top_k=int(os.environ.get("RAG_DEFAULT_TOP_K", "5")),
    )


settings = _load_settings()
