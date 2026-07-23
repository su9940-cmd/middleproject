"""rag_agent 및 rag_service 단위 테스트.

Vector store는 가짜 구현으로 대체해 검색 계약을 검증한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.rag import build_query_text, rag_agent
from app.core.enums import MachineType, RiskLevel
from app.services.rag_service import (
    RetrievalRequest,
    normalize_retrieved_documents,
    resolve_manual_id,
    retrieve_documents,
)


class FakeVectorStore:
    """테스트용 가짜 Vector store."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.last_filter: dict[str, Any] | None = None

    def query(
        self,
        query_text: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        self.last_filter = metadata_filter
        return self.results[:top_k]


def test_resolve_manual_id_prefers_explicit() -> None:
    assert (
        resolve_manual_id("M-0101", MachineType.REACTOR, "custom_manual")
        == "custom_manual"
    )


def test_resolve_manual_id_by_machine_id() -> None:
    assert (
        resolve_manual_id("M-0104", MachineType.PUMP)
        == "pump_safety_manual"
    )


def test_resolve_manual_id_raises_when_unknown() -> None:
    with pytest.raises(ValueError):
        resolve_manual_id("M-9999", "UNKNOWN")  # type: ignore[arg-type]


def test_normalize_drops_incomplete_chunks() -> None:
    raw = [
        {
            "source_id": "s1",
            "document_type": "sop",
            "title": "t1",
            "content": "c1",
        },
        {"source_id": "s2", "title": "no content"},  # 필수 결손 → 제외
    ]
    normalized = normalize_retrieved_documents(raw)
    assert len(normalized) == 1
    assert normalized[0]["section"] is None
    assert normalized[0]["relevance_score"] is None


def test_retrieve_documents_applies_manual_filter() -> None:
    store = FakeVectorStore(
        [
            {
                "source_id": "s1",
                "document_type": "sop",
                "title": "펌프 최소유량",
                "content": "최소 유량 30% 유지",
            }
        ]
    )
    request = RetrievalRequest(
        machine_id="M-0104",
        machine_type=MachineType.PUMP,
        query_text="펌프 최소 유량",
    )
    docs = retrieve_documents(store, request)
    assert store.last_filter == {"manual_id": "pump_safety_manual"}
    assert docs[0]["document_type"] == "sop"


def test_build_query_text_includes_emergency_reasons() -> None:
    state = {
        "machine_type": MachineType.REACTOR,
        "risk_level": RiskLevel.EMERGENCY,
        "emergency_reasons": ["온도 폭주"],
    }
    query = build_query_text(state)
    assert "REACTOR" in query
    assert "온도 폭주" in query


def test_rag_agent_returns_error_contract_on_missing_ids() -> None:
    result = rag_agent({"risk_level": RiskLevel.WARNING})
    assert result["error_code"] == "RAG_RETRIEVAL_FAILED"
    assert result["failed_node"] == "rag_agent"
    assert result["retrieved_documents"] == []
