"""RAG retrieval contracts and service-level policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.enums import MachineType


DEFAULT_TOP_K = 5

MACHINE_MANUAL_MAP: dict[str, str] = {
    "M-0101": "reactor_safety_manual",
    "M-0102": "compressor_safety_manual",
    "M-0103": "storage_tank_safety_manual",
    "M-0104": "pump_safety_manual",
}

MACHINE_TYPE_MANUAL_MAP: dict[MachineType, str] = {
    MachineType.REACTOR: "reactor_safety_manual",
    MachineType.COMPRESSOR: "compressor_safety_manual",
    MachineType.STORAGE_TANK: "storage_tank_safety_manual",
    MachineType.PUMP: "pump_safety_manual",
}


class VectorStore(Protocol):
    """Minimal interface required from a vector-store adapter."""

    def query(
        self,
        query_text: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class RetrievalRequest:
    machine_id: str
    machine_type: MachineType
    query_text: str
    manual_id: str | None = None
    top_k: int = DEFAULT_TOP_K


def resolve_manual_id(
    machine_id: str | None,
    machine_type: MachineType | str | None,
    manual_id: str | None = None,
) -> str:
    """Resolve the SOP id from explicit state, type, then machine id."""

    if manual_id and manual_id.strip():
        return manual_id.strip()

    if machine_type is not None:
        try:
            normalized_type = MachineType(machine_type)
        except ValueError:
            normalized_type = None
        if normalized_type in MACHINE_TYPE_MANUAL_MAP:
            return MACHINE_TYPE_MANUAL_MAP[normalized_type]

    normalized_id = machine_id.strip() if machine_id else ""
    if normalized_id in MACHINE_MANUAL_MAP:
        return MACHINE_MANUAL_MAP[normalized_id]

    raise ValueError(
        "manual could not be resolved: "
        f"machine_id={machine_id}, machine_type={machine_type}"
    )


def build_metadata_filter(
    manual_id: str,
    document_type: str | None = None,
) -> dict[str, Any]:
    """Build a Chroma 1.x-compatible equality filter.

    Laws are duplicated per applicable machine manual during indexing, so both
    SOP and law queries can use the same scalar ``manual_id`` equality filter.
    """

    if not document_type:
        return {"manual_id": manual_id}
    return {
        "$and": [
            {"manual_id": manual_id},
            {"document_type": document_type.strip().lower()},
        ]
    }


def normalize_retrieved_documents(
    raw_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize vector-store rows to the shared RAG document contract."""

    normalized: list[dict[str, Any]] = []
    for item in raw_results:
        source_id = str(item.get("source_id") or "").strip()
        document_type = str(item.get("document_type") or "").strip().lower()
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if not all((source_id, document_type, title, content)):
            continue
        normalized.append(
            {
                "source_id": source_id,
                "document_type": document_type,
                "title": title,
                "section": item.get("section"),
                "content": content,
                "relevance_score": item.get("relevance_score"),
                "manual_version": item.get("manual_version"),
            }
        )
    return normalized


def retrieve_documents(
    vector_store: VectorStore,
    request: RetrievalRequest,
) -> list[dict[str, Any]]:
    """Retrieve both executable SOP evidence and supporting law evidence.

    A single mixed top-k query can return only laws and leave Action Draft with
    no executable SOP.  The budget is therefore split between the two document
    types and the valid results are merged by relevance afterwards.
    """

    manual_id = resolve_manual_id(
        machine_id=request.machine_id,
        machine_type=request.machine_type,
        manual_id=request.manual_id,
    )
    total_top_k = max(1, int(request.top_k or DEFAULT_TOP_K))
    sop_top_k, law_top_k = _split_top_k(total_top_k)

    raw_results = vector_store.query(
        query_text=request.query_text,
        top_k=sop_top_k,
        metadata_filter=build_metadata_filter(manual_id, "sop"),
    )
    if law_top_k:
        raw_results.extend(
            vector_store.query(
                query_text=request.query_text,
                top_k=law_top_k,
                metadata_filter=build_metadata_filter(manual_id, "law"),
            )
        )

    normalized = normalize_retrieved_documents(raw_results)
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for document in normalized:
        key = (
            document["source_id"],
            str(document.get("section") or ""),
            document["content"],
        )
        unique.setdefault(key, document)
    return sorted(
        unique.values(),
        key=lambda document: _score(document.get("relevance_score")),
        reverse=True,
    )[:total_top_k]


def _split_top_k(total_top_k: int) -> tuple[int, int]:
    if total_top_k == 1:
        return 1, 0
    sop_top_k = (total_top_k + 1) // 2
    return sop_top_k, total_top_k - sop_top_k


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0
