"""Integration tests for final graph routing with injected team-node fakes."""

import unittest
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.core.enums import AlertStatus, MeasurementMode, RiskLevel
from app.graph.builder import GraphDependencies, build_safety_graph, graph_config
from app.nodes.recovery import recovery_node


class GraphBuilderIntegrationTest(unittest.TestCase):
    """Verify normal, abnormal, emergency, fan-out/fan-in, and recheck flow."""

    def setUp(self) -> None:
        self.events: list[str] = []

    def _recording_node(
        self,
        name: str,
        result: dict[str, Any] | Callable[[dict], dict[str, Any]],
    ):
        def node(state: dict) -> dict[str, Any]:
            self.events.append(name)
            return result(state) if callable(result) else dict(result)

        return node

    def _dependencies(self, initial_risk: RiskLevel) -> GraphDependencies:
        def predictive_result(state: dict) -> dict[str, Any]:
            is_recheck = state.get("measurement_mode") == MeasurementMode.IMMEDIATE_RECHECK
            return {
                "ml_risk_score": 0.1 if is_recheck else 0.3,
                "model_version": "fake-model",
                "prediction_thresholds": {"caution": 0.145, "warning": 0.29},
                "error_code": None,
                "error_message": None,
                "failed_node": None,
            }

        def policy_result(state: dict) -> dict[str, Any]:
            is_recheck = state.get("measurement_mode") == MeasurementMode.IMMEDIATE_RECHECK
            return {
                "risk_level": (
                    RiskLevel.NORMAL.value if is_recheck else initial_risk.value
                ),
                "emergency_reasons": ["TEST_EMERGENCY"]
                if initial_risk is RiskLevel.EMERGENCY and not is_recheck
                else [],
                "policy_version": "fake-policy",
                "error_code": None,
                "error_message": None,
                "failed_node": None,
            }

        def action_result(state: dict) -> dict[str, Any]:
            self.assertIn("retrieved_documents", state)
            self.assertIn("memory_context", state)
            return {"action_draft": {"action_phase": "INITIAL"}}

        return GraphDependencies(
            predictive_agent=self._recording_node("predictive", predictive_result),
            risk_policy=self._recording_node("risk_policy", policy_result),
            recovery_node=self._recording_node("recovery", recovery_node),
            rag_agent=self._recording_node(
                "rag", {"retrieved_documents": [{"source_id": "test-sop"}]}
            ),
            memory_agent=self._recording_node(
                "memory", {"memory_context": {"previous_alert_count": 0}}
            ),
            action_draft_node=self._recording_node("action", action_result),
            validator_agent=self._recording_node(
                "validator", {"final_checklist": {"items": []}}
            ),
            send_immediate_alert=self._recording_node(
                "immediate_alert", {"notification_status": "SENT"}
            ),
            worker_interrupt=self._recording_node(
                "worker_interrupt", {"worker_response": {"submitted": True}}
            ),
            request_immediate_recheck=self._recording_node(
                "immediate_recheck",
                {
                    "measurement_mode": MeasurementMode.IMMEDIATE_RECHECK.value,
                    "alert_status": AlertStatus.WAITING_RECHECK.value,
                    "sensor_reading": {"test": "rechecked"},
                },
            ),
        )

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "thread_id": "M-0101:AL-TEST",
            "machine_id": "M-0101",
            "measurement_mode": MeasurementMode.PERIODIC.value,
            "alert_status": AlertStatus.OPEN.value,
            "consecutive_normal_count": 0,
            "sensor_reading": {"test": "initial"},
        }

    def test_normal_path_ends_without_context_agents(self) -> None:
        graph = build_safety_graph(
            self._dependencies(RiskLevel.NORMAL), checkpointer=InMemorySaver()
        )

        result = graph.invoke(
            self._initial_state(), graph_config("M-0101:AL-NORMAL")
        )

        self.assertEqual(self.events, ["predictive", "risk_policy", "recovery"])
        self.assertEqual(result["alert_status"], AlertStatus.MONITORING)

    def test_abnormal_path_joins_context_then_rechecks(self) -> None:
        graph = build_safety_graph(
            self._dependencies(RiskLevel.WARNING), checkpointer=InMemorySaver()
        )

        result = graph.invoke(
            self._initial_state(), graph_config("M-0101:AL-WARNING")
        )

        self.assertIn("rag", self.events)
        self.assertIn("memory", self.events)
        self.assertLess(self.events.index("rag"), self.events.index("action"))
        self.assertLess(self.events.index("memory"), self.events.index("action"))
        self.assertIn("worker_interrupt", self.events)
        self.assertIn("immediate_recheck", self.events)
        self.assertNotIn("immediate_alert", self.events)
        self.assertEqual(result["risk_level"], RiskLevel.NORMAL)
        self.assertEqual(result["alert_status"], AlertStatus.MONITORING)

    def test_emergency_adds_immediate_alert_without_skipping_checklist(self) -> None:
        graph = build_safety_graph(
            self._dependencies(RiskLevel.EMERGENCY), checkpointer=InMemorySaver()
        )

        result = graph.invoke(
            self._initial_state(), graph_config("M-0101:AL-EMERGENCY")
        )

        self.assertIn("immediate_alert", self.events)
        self.assertIn("rag", self.events)
        self.assertIn("memory", self.events)
        self.assertIn("validator", self.events)
        self.assertIn("worker_interrupt", self.events)
        self.assertEqual(result["notification_status"], "SENT")

    def test_graph_config_rejects_empty_thread_id(self) -> None:
        with self.assertRaises(ValueError):
            graph_config("   ")


if __name__ == "__main__":
    unittest.main()
