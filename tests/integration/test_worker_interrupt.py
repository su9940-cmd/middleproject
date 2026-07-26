"""Real LangGraph interrupt/resume integration tests."""

import unittest
from datetime import datetime
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.core.enums import AlertStatus, MeasurementMode, RiskLevel
from app.core.exceptions import WorkerResponseValidationError
from app.graph.builder import GraphDependencies, build_safety_graph
from app.graph.execution import resume_worker_interrupt, start_incident
from app.nodes.recovery import recovery_node


class WorkerInterruptIntegrationTest(unittest.TestCase):
    """Verify pause, checkpoint, same-thread resume, and recheck continuation."""

    @staticmethod
    def _dependencies() -> GraphDependencies:
        def predictive(state: dict) -> dict[str, Any]:
            is_recheck = state.get("measurement_mode") == MeasurementMode.IMMEDIATE_RECHECK
            return {
                "ml_risk_score": 0.1 if is_recheck else 0.3,
                "model_version": "fake-model",
                "prediction_thresholds": {"caution": 0.145, "warning": 0.29},
                "error_code": None,
                "error_message": None,
                "failed_node": None,
            }

        def policy(state: dict) -> dict[str, Any]:
            is_recheck = state.get("measurement_mode") == MeasurementMode.IMMEDIATE_RECHECK
            return {
                "risk_level": (
                    RiskLevel.NORMAL.value
                    if is_recheck
                    else RiskLevel.WARNING.value
                ),
                "emergency_reasons": [],
                "policy_version": "fake-policy",
                "error_code": None,
                "error_message": None,
                "failed_node": None,
            }

        return GraphDependencies(
            predictive_agent=predictive,
            risk_policy=policy,
            recovery_node=recovery_node,
            rag_agent=lambda state: {
                "retrieved_documents": [{"source_id": "test-sop"}]
            },
            memory_agent=lambda state: {
                "memory_context": {"previous_alert_count": 0}
            },
            action_draft_node=lambda state: {
                "action_draft": {"action_phase": "INITIAL"}
            },
            validator_agent=lambda state: {
                "final_checklist": {
                    "checklist_id": "CL-AL-TEST-V1",
                    "alert_id": "AL-TEST",
                    "version": 1,
                    "items": [
                        {
                            "checklist_item_id": "ITEM-1",
                            "title": "관리자 보고",
                        }
                    ],
                }
            },
            send_immediate_alert=lambda state: {
                "notification_status": "SENT"
            },
            request_immediate_recheck=lambda state: {
                "measurement_mode": MeasurementMode.IMMEDIATE_RECHECK.value,
                "alert_status": AlertStatus.WAITING_RECHECK.value,
                "sensor_reading": {"test": "rechecked"},
            },
        )

    @staticmethod
    def _initial_state(thread_id: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "thread_id": thread_id,
            "alert_id": "AL-TEST",
            "machine_id": "M-0101",
            "machine_type": "REACTOR",
            "measurement_mode": MeasurementMode.PERIODIC.value,
            "alert_status": AlertStatus.OPEN.value,
            "consecutive_normal_count": 0,
            "sensor_reading": {"test": "initial"},
        }

    @staticmethod
    def _response(**overrides: Any) -> dict[str, Any]:
        payload = {
            "response_id": "RP-TEST",
            "alert_id": "AL-TEST",
            "checklist_id": "CL-AL-TEST-V1",
            "worker_id": "WORKER-01",
            "submitted_at": datetime.fromisoformat("2026-07-23T11:00:00+09:00"),
            "item_results": [
                {
                    "checklist_item_id": "ITEM-1",
                    "status": "COMPLETED",
                    "worker_note": "관리자 보고 완료",
                    "completed_at": "2026-07-23T10:59:00+09:00",
                }
            ],
            "overall_note": "현장 조치 완료",
            "evidence_urls": [],
        }
        payload.update(overrides)
        return payload

    def test_graph_pauses_and_resumes_with_same_thread(self) -> None:
        graph = build_safety_graph(
            self._dependencies(), checkpointer=InMemorySaver()
        )
        thread_id = "M-0101:AL-TEST"

        paused = start_incident(
            graph, self._initial_state(thread_id), thread_id=thread_id
        )

        self.assertIn("__interrupt__", paused)
        interrupt_value = paused["__interrupt__"][0].value
        self.assertEqual(interrupt_value["interrupt_type"], "WORKER_CHECKLIST")
        self.assertEqual(interrupt_value["alert_id"], "AL-TEST")
        self.assertEqual(
            interrupt_value["final_checklist"]["checklist_id"],
            "CL-AL-TEST-V1",
        )

        resumed = resume_worker_interrupt(
            graph, self._response(), thread_id=thread_id
        )

        self.assertEqual(resumed["worker_response"]["worker_id"], "WORKER-01")
        self.assertEqual(resumed["measurement_mode"], MeasurementMode.IMMEDIATE_RECHECK)
        self.assertEqual(resumed["risk_level"], RiskLevel.WARNING.value)
        self.assertEqual(resumed["alert_status"], AlertStatus.WAITING_RECHECK.value)
        self.assertEqual(resumed["consecutive_normal_count"], 0)

    def test_resume_rejects_mismatched_alert_id(self) -> None:
        graph = build_safety_graph(
            self._dependencies(), checkpointer=InMemorySaver()
        )
        thread_id = "M-0101:AL-TEST-MISMATCH"
        start_incident(graph, self._initial_state(thread_id), thread_id=thread_id)

        with self.assertRaises(WorkerResponseValidationError):
            resume_worker_interrupt(
                graph,
                self._response(alert_id="AL-OTHER"),
                thread_id=thread_id,
            )

    def test_resume_rejects_unknown_checklist_item(self) -> None:
        graph = build_safety_graph(
            self._dependencies(), checkpointer=InMemorySaver()
        )
        thread_id = "M-0101:AL-TEST-ITEM-MISMATCH"
        start_incident(graph, self._initial_state(thread_id), thread_id=thread_id)
        response = self._response()
        response["item_results"][0]["checklist_item_id"] = "ITEM-OTHER"

        with self.assertRaises(WorkerResponseValidationError):
            resume_worker_interrupt(graph, response, thread_id=thread_id)

    def test_different_thread_cannot_resume_checkpoint(self) -> None:
        graph = build_safety_graph(
            self._dependencies(), checkpointer=InMemorySaver()
        )
        start_incident(
            graph,
            self._initial_state("M-0101:AL-TEST-ORIGINAL"),
            thread_id="M-0101:AL-TEST-ORIGINAL",
        )

        with self.assertRaises(Exception):
            resume_worker_interrupt(
                graph,
                self._response(),
                thread_id="M-0101:AL-DIFFERENT",
            )


if __name__ == "__main__":
    unittest.main()
