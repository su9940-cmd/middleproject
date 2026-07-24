"""Unit tests for the RAG agent and retrieval service contracts."""

from __future__ import annotations

import unittest
from typing import Any

from app.agents.rag import build_query_text, rag_agent
from app.core.enums import MachineType, RiskLevel
from app.services.rag_service import (
    RetrievalRequest,
    normalize_retrieved_documents,
    resolve_manual_id,
    retrieve_documents,
)


class FakeVectorStore:
    """Small vector-store double used by retrieval tests."""

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


class RAGAgentTest(unittest.TestCase):
    def test_resolve_manual_id_prefers_explicit(self) -> None:
        self.assertEqual(
            resolve_manual_id("M-0101", MachineType.REACTOR, "custom_manual"),
            "custom_manual",
        )

    def test_resolve_manual_id_by_machine_id(self) -> None:
        self.assertEqual(
            resolve_manual_id("M-0104", MachineType.PUMP),
            "pump_safety_manual",
        )

    def test_resolve_manual_id_raises_when_unknown(self) -> None:
        with self.assertRaises(ValueError):
            resolve_manual_id("M-9999", "UNKNOWN")  # type: ignore[arg-type]

    def test_normalize_drops_incomplete_chunks(self) -> None:
        raw = [
            {
                "source_id": "s1",
                "document_type": "sop",
                "title": "t1",
                "content": "c1",
            },
            {"source_id": "s2", "title": "no content"},
        ]
        normalized = normalize_retrieved_documents(raw)
        self.assertEqual(len(normalized), 1)
        self.assertIsNone(normalized[0]["section"])
        self.assertIsNone(normalized[0]["relevance_score"])

    def test_retrieve_documents_applies_manual_filter(self) -> None:
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
        documents = retrieve_documents(store, request)
        self.assertEqual(
            store.last_filter,
            {
                "$and": [
                    {"manual_id": "pump_safety_manual"},
                    {"document_type": {"$in": ["sop", "law"]}},
                ]
            },
        )
        self.assertEqual(documents[0]["document_type"], "sop")

    def test_build_query_text_includes_emergency_reasons(self) -> None:
        state = {
            "machine_type": MachineType.REACTOR,
            "risk_level": RiskLevel.EMERGENCY,
            "emergency_reasons": ["온도 초과"],
        }
        query = build_query_text(state)
        self.assertIn("REACTOR", query)
        self.assertIn("온도 초과", query)

    def test_rag_agent_returns_error_contract_on_missing_ids(self) -> None:
        result = rag_agent({"risk_level": RiskLevel.WARNING})
        self.assertEqual(result["error_code"], "RAG_RETRIEVAL_FAILED")
        self.assertEqual(result["failed_node"], "rag_agent")
        self.assertEqual(result["retrieved_documents"], [])


if __name__ == "__main__":
    unittest.main()
