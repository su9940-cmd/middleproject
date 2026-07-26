"""Context-retrieval RAG node for abnormal equipment readings."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import RAGRetrievalError
from app.graph.state import SafetyState
from app.services.rag_service import RetrievalRequest, retrieve_documents
from app.services.vector_store_factory import get_vector_store


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
