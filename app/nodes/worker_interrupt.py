"""Worker Interrupt - pauses the graph until a worker submits a checklist response.

Not one of the ten nodes with a committed output shape in the shared
contract (section 8 lists Predictive/Risk Policy/Recovery/RAG/Memory/Action
Draft/Validator/Immediate Alert/Immediate Recheck only), but its single
output field, `worker_response`, is already reserved on `SafetyState`.
Resuming happens through `POST /worker/checklists/{checklist_id}/respond`
(`app.api.worker_routes`), which resolves the checklist's `thread_id` and
calls `graph.ainvoke(Command(resume=response), config=...)` on that same
thread - see that module for the full resume sequence.

The `interrupt()` payload shape below is aligned with role E's
`WorkerInterruptScreen` component, which reads `state.machine_id`/
`machine_type`/`measured_at`/`ml_risk_score`/`emergency_reasons`/
`notification_status`/`immediate_alert_sent_at`/`final_checklist` directly
off the interrupt value - field-for-field, not just `alert_id`/`final_checklist`.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.graph.state import SafetyState


def worker_interrupt(state: SafetyState) -> dict[str, Any]:
    """Pause and surface the incident context until a worker responds.

    Reads `alert_id`, `machine_id`, `machine_type`, `measured_at`,
    `risk_level`, `ml_risk_score`, `emergency_reasons`, `final_checklist`,
    `notification_status`, `immediate_alert_sent_at` from `state`. Blocks
    (via `langgraph.types.interrupt`) until the run is resumed with
    `Command(resume=<worker_response dict>)`, then returns that value
    verbatim under `worker_response`.
    """

    worker_response = interrupt(
        {
            "alert_id": state.get("alert_id"),
            "machine_id": state.get("machine_id"),
            "machine_type": state.get("machine_type"),
            "measured_at": state.get("measured_at"),
            "risk_level": state.get("risk_level"),
            "ml_risk_score": state.get("ml_risk_score"),
            "emergency_reasons": state.get("emergency_reasons", []),
            "final_checklist": state.get("final_checklist"),
            "notification_status": state.get("notification_status"),
            "immediate_alert_sent_at": state.get("immediate_alert_sent_at"),
        }
    )
    return {"worker_response": worker_response}
