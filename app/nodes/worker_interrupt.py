"""Worker Interrupt - pauses the graph until a worker submits a checklist response.

Not one of the ten nodes with a committed output shape in the shared
contract (section 8 lists Predictive/Risk Policy/Recovery/RAG/Memory/Action
Draft/Validator/Immediate Alert/Immediate Recheck only), but its single
output field, `worker_response`, is already reserved on `SafetyState`.
Resuming happens through `POST /worker/checklists/{checklist_id}/respond`
(`app.api.worker_routes`), which resolves the checklist's `thread_id` and
calls `graph.ainvoke(Command(resume=response), config=...)` on that same
thread - see that module for the full resume sequence.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.graph.state import SafetyState


def worker_interrupt(state: SafetyState) -> dict[str, Any]:
    """Pause and surface the final checklist until a worker responds.

    Reads `alert_id`, `final_checklist` from `state`. Blocks (via
    `langgraph.types.interrupt`) until the run is resumed with
    `Command(resume=<worker_response dict>)`, then returns that value
    verbatim under `worker_response`.
    """

    worker_response = interrupt(
        {
            "alert_id": state.get("alert_id"),
            "checklist_id": (state.get("final_checklist") or {}).get("checklist_id"),
            "final_checklist": state.get("final_checklist"),
        }
    )
    return {"worker_response": worker_response}
