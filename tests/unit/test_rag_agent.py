"""Unit tests for RAG query and retrieval contracts."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from app.agents.rag import build_query_text, rag_agent
from app.core.enums import MachineType, RiskLevel
from app.services.rag_service import (
    RetrievalRequest,
    normalize_retrieved_documents,
    resolve_manual_id,
    retrieve_documents,
)


class FakeVectorStore:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.calls: list[dict[str, Any] | None] = []

    def query(
        self,
        query_text: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        self.calls.append(metadata_filter)
        document_type = None
        if metadata_filter and "$and" in metadata_filter:
            document_type = metadata_filter["$and"][1].get("document_type")
        matching = [
            result
            for result in self.results
            if document_type is None or result.get("document_type") == document_type
        ]
        return matching[:top_k]


class RAGAgentTest(unittest.TestCase):
    def test_resolve_manual_id_contract(self) -> None:
        self.assertEqual(
            resolve_manual_id("M-0101", MachineType.REACTOR, "custom_manual"),
            "custom_manual",
        )
        self.assertEqual(
            resolve_manual_id("M-0104", MachineType.PUMP),
            "pump_safety_manual",
        )
        with self.assertRaises(ValueError):
            resolve_manual_id("M-9999", "UNKNOWN")

    def test_normalize_drops_incomplete_chunks_and_lowercases_type(self) -> None:
        normalized = normalize_retrieved_documents(
            [
                {
                    "source_id": "s1",
                    "document_type": "SOP",
                    "title": "title",
                    "content": "content",
                },
                {"source_id": "s2", "title": "incomplete"},
            ]
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["document_type"], "sop")
        self.assertIsNone(normalized[0]["section"])

    def test_retrieval_guarantees_sop_and_law_budgets(self) -> None:
        store = FakeVectorStore(
            [
                {
                    "source_id": "sop1",
                    "document_type": "sop",
                    "title": "Pump procedure",
                    "content": "Inspect the inlet valve.",
                    "relevance_score": 0.9,
                },
                {
                    "source_id": "law1",
                    "document_type": "law",
                    "title": "Lockout law",
                    "content": "Apply lockout before maintenance.",
                    "relevance_score": 0.8,
                },
            ]
        )
        documents = retrieve_documents(
            store,
            RetrievalRequest(
                machine_id="M-0104",
                machine_type=MachineType.PUMP,
                query_text="pump vibration",
            ),
        )

        self.assertEqual(len(store.calls), 2)
        self.assertEqual(store.calls[0]["$and"][0], {"manual_id": "pump_safety_manual"})
        self.assertEqual(store.calls[0]["$and"][1], {"document_type": "sop"})
        self.assertEqual(store.calls[1]["$and"][1], {"document_type": "law"})
        self.assertEqual({doc["document_type"] for doc in documents}, {"sop", "law"})

    def test_query_includes_incident_sensor_context(self) -> None:
        query = build_query_text(
            {
                "machine_type": MachineType.PUMP,
                "risk_level": RiskLevel.WARNING,
                "ml_risk_score": 0.72,
                "sensor_reading": {"vibration": 5.2, "pressure": 9.8},
                "emergency_reasons": ["PUMP_VIBRATION_HIGH"],
            }
        )
        self.assertIn("PUMP", query)
        self.assertIn("vibration=5.2", query)
        self.assertIn("pressure=9.8", query)
        self.assertIn("ML risk score=0.72", query)
        self.assertIn("PUMP_VIBRATION_HIGH", query)

    def test_rag_agent_error_contracts(self) -> None:
        missing = rag_agent({"risk_level": RiskLevel.WARNING})
        self.assertEqual(missing["error_code"], "RAG_RETRIEVAL_FAILED")

        law_only_store = FakeVectorStore(
            [{
                "source_id": "law1",
                "document_type": "law",
                "title": "law",
                "content": "legal reference",
            }]
        )
        with patch("app.agents.rag.get_vector_store", return_value=law_only_store):
            law_only = rag_agent(
                {
                    "machine_id": "M-0104",
                    "machine_type": MachineType.PUMP,
                    "risk_level": RiskLevel.WARNING,
                    "sensor_reading": {"vibration": 5.2},
                }
            )
        self.assertEqual(law_only["error_code"], "RAG_RETRIEVAL_FAILED")
        self.assertEqual(law_only["retrieved_documents"], [])


if __name__ == "__main__":
    unittest.main()
