"""Context-retrieval RAG node for abnormal equipment readings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.exceptions import RAGRetrievalError
from app.graph.state import SafetyState
from app.services.rag_service import RetrievalRequest, resolve_manual_id, retrieve_documents
from app.services.vector_store_factory import get_vector_store


def _parse_law_front_matter(text: str) -> dict[str, Any]:
    """Pull the `article`/`law_name`/`title` front-matter fields off a law markdown file.

    Mirrors `scripts/index_documents.py::parse_front_matter` - duplicated here
    (rather than imported) since `scripts/` isn't a library the app package
    depends on.
    """

    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def build_query_text(state: SafetyState) -> str:
    """Build an incident-specific query from risk and sensor context."""

    parts: list[str] = []
    machine_type = state.get("machine_type")
    if machine_type is not None:
        parts.append(str(machine_type))

    risk_level = state.get("risk_level")
    if risk_level is not None:
        parts.append(f"{risk_level} response procedure")

    emergency_reasons = state.get("emergency_reasons") or []
    if emergency_reasons:
        parts.append("emergency reasons: " + ", ".join(map(str, emergency_reasons)))

    ml_risk_score = state.get("ml_risk_score")
    if ml_risk_score is not None:
        parts.append(f"ML risk score={ml_risk_score}")

    sensor_context = _sensor_context(state.get("sensor_reading") or {})
    if sensor_context:
        parts.append("sensor readings: " + sensor_context)

    risk_evidence = state.get("risk_evidence") or []
    if risk_evidence:
        parts.append("risk evidence: " + "; ".join(map(str, risk_evidence)))

    return " / ".join(parts) if parts else "equipment safety response procedure"


def rag_agent(state: SafetyState) -> dict[str, Any]:
    """Retrieve grounded SOP and supporting law chunks for one incident."""

    machine_id = state.get("machine_id")
    machine_type = state.get("machine_type")
    if machine_id is None or machine_type is None:
        return _error("machine_id and machine_type are required for RAG retrieval")

    try:
        request = RetrievalRequest(
            machine_id=machine_id,
            machine_type=machine_type,
            query_text=build_query_text(state),
            manual_id=state.get("manual_id"),
        )
        documents = retrieve_documents(get_vector_store(), request)
    except Exception as exc:  # Provider-specific vector DB errors are normalized here.
        # The local API demo may be started before Chroma indexing.  Use the
        # checked-in SOP/law files as a deterministic fallback; a production
        # deployment should index them and use the vector store path.
        try:
            fallback_manual_id = resolve_manual_id(
                request.machine_id, request.machine_type, request.manual_id
            )
        except ValueError:
            fallback_manual_id = ""
        documents = _load_local_documents(fallback_manual_id)
        if not documents:
            return _error(f"document retrieval failed: {exc}")

    if not any(
        str(document.get("document_type") or "").lower() == "sop"
        for document in documents
    ):
        return _error("no grounded SOP document was retrieved")
    return {
        "retrieved_documents": documents,
        "error_code": None,
        "error_message": None,
        "failed_node": None,
    }


def _sensor_context(sensor_reading: dict[str, Any]) -> str:
    excluded_fields = {
        "reading_id",
        "machine_id",
        "machine_type",
        "measured_at",
        "measurement_mode",
    }
    values = [
        f"{key}={value}"
        for key, value in sorted(sensor_reading.items())
        if key not in excluded_fields and value is not None
    ]
    return ", ".join(values)


def _error(message: str) -> dict[str, Any]:
    return {
        "error_code": RAGRetrievalError.error_code,
        "error_message": message,
        "failed_node": "rag_agent",
        "retrieved_documents": [],
    }


def _load_local_documents(manual_id: str) -> list[dict[str, Any]]:
    """Load the machine SOP and a small law reference set for local demos."""

    project_root = Path(__file__).resolve().parents[2]
    documents: list[dict[str, Any]] = []
    sop_path = project_root / "data" / "sop" / f"{manual_id}.md"
    if sop_path.is_file():
        documents.append(
            {
                "source_id": manual_id,
                "document_type": "sop",
                "title": sop_path.stem,
                "section": None,
                "section_id": f"{manual_id}:full",
                "action_level": "STANDARD",
                "risk_level_tags": None,
                "source_path": str(sop_path),
                "legal_reference": None,
                "content": sop_path.read_text(encoding="utf-8"),
                "relevance_score": 1.0,
                "manual_version": None,
            }
        )

    law_dir = project_root / "data" / "laws"
    for law_path in sorted(law_dir.glob("*.md"))[:2]:
        law_text = law_path.read_text(encoding="utf-8")
        front_matter = _parse_law_front_matter(law_text)
        article = front_matter.get("article")
        # Same title/legal_reference shape as the real Chroma-indexed path
        # (scripts/index_documents.py::build_law_records) so both retrieval
        # paths render identically in the UI.
        title = (
            f"{front_matter.get('law_name', '')} {article or ''} "
            f"({front_matter.get('title', '')})"
        ).strip() or law_path.stem
        documents.append(
            {
                "source_id": front_matter.get("source_id") or law_path.stem,
                "document_type": "law",
                "title": title,
                "section": article,
                "section_id": f"{law_path.stem}:full",
                "action_level": "REFERENCE",
                "risk_level_tags": None,
                "source_path": str(law_path),
                "legal_reference": front_matter.get("legal_reference") or article or law_path.stem,
                "content": law_text,
                "relevance_score": 0.5,
                "manual_version": None,
            }
        )
    return documents
