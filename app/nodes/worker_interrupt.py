"""LangGraph human-in-the-loop node for worker checklist completion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from langgraph.types import interrupt
from pydantic import ValidationError
from pydantic_core import to_jsonable_python

from app.core.exceptions import (
    ChecklistValidationError,
    WorkerResponseValidationError,
)
from app.graph.state import SafetyState
from app.models.worker import WorkerResumePayload


INTERRUPT_TYPE = "WORKER_CHECKLIST"


def worker_interrupt(state: SafetyState) -> dict[str, Any]:
    """Pause the graph for worker action and validate the resume payload."""

    alert_id, checklist_id, interrupt_value = _build_interrupt_value(state)
    raw_response = interrupt(interrupt_value)

    try:
        response = WorkerResumePayload.model_validate(
            _normalize_worker_response(raw_response, checklist_id=checklist_id)
        )
    except ValidationError as exc:
        raise WorkerResponseValidationError(
            "worker resume payload validation failed",
            details={"validation_errors": exc.errors(include_url=False)},
        ) from exc

    if response.alert_id != alert_id:
        raise WorkerResponseValidationError(
            "worker response alert_id does not match the interrupted incident",
            details={"expected": alert_id, "received": response.alert_id},
        )
    if response.checklist_id != checklist_id:
        raise WorkerResponseValidationError(
            "worker response checklist_id does not match the interrupted checklist",
            details={"expected": checklist_id, "received": response.checklist_id},
        )

    _validate_item_results(response, state["final_checklist"])

    return {"worker_response": response.model_dump(mode="json")}


def _build_interrupt_value(
    state: SafetyState,
) -> tuple[str, str, dict[str, Any]]:
    alert_id = state.get("alert_id")
    machine_id = state.get("machine_id")
    final_checklist = state.get("final_checklist")

    if not alert_id:
        raise ChecklistValidationError("alert_id is required before worker interrupt")
    if not machine_id:
        raise ChecklistValidationError("machine_id is required before worker interrupt")
    if not isinstance(final_checklist, Mapping):
        raise ChecklistValidationError("final_checklist must be available before interrupt")

    checklist_id = final_checklist.get("checklist_id")
    if not isinstance(checklist_id, str) or not checklist_id.strip():
        raise ChecklistValidationError("final_checklist.checklist_id is required")

    return (
        alert_id,
        checklist_id,
        to_jsonable_python(
            {
                "interrupt_type": INTERRUPT_TYPE,
                "thread_id": state.get("thread_id"),
                "alert_id": alert_id,
                "machine_id": machine_id,
                "machine_type": state.get("machine_type"),
                "risk_level": state.get("risk_level"),
                "ml_risk_score": state.get("ml_risk_score"),
                "emergency_reasons": state.get("emergency_reasons", []),
                "notification_status": state.get("notification_status"),
                "immediate_alert_sent_at": state.get("immediate_alert_sent_at"),
                "final_checklist": dict(final_checklist),
            }
        ),
    )


def _validate_item_results(
    response: WorkerResumePayload,
    final_checklist: Mapping[str, Any],
) -> None:
    checklist_items = final_checklist.get("items")
    if not isinstance(checklist_items, list):
        raise ChecklistValidationError("final_checklist.items must be a list")
    # A legacy/mock checklist may have no item rows.  The response itself is
    # still valid; there are simply no item IDs to compare.
    if not checklist_items:
        return

    expected_ids = {
        item.get("checklist_item_id")
        for item in checklist_items
        if isinstance(item, Mapping) and item.get("checklist_item_id")
    }
    if len(expected_ids) != len(checklist_items):
        raise ChecklistValidationError(
            "every final checklist item must have a unique checklist_item_id"
        )

    received_ids = [item.checklist_item_id for item in response.item_results]
    if len(received_ids) != len(set(received_ids)):
        raise WorkerResponseValidationError(
            "worker response contains duplicate checklist item results"
        )

    missing_ids = sorted(expected_ids - set(received_ids))
    unknown_ids = sorted(set(received_ids) - expected_ids)
    if missing_ids or unknown_ids:
        raise WorkerResponseValidationError(
            "worker response checklist items do not match the interrupted checklist",
            details={"missing_ids": missing_ids, "unknown_ids": unknown_ids},
        )


def _normalize_worker_response(raw_response: Any, *, checklist_id: str) -> Any:
    """Accept the UI's compact ``item_statuses`` payload as well as the
    canonical ``item_results`` contract.

    The UI only needs to submit a status map and a note.  Normalize it at the
    graph boundary so the rest of the system stores one stable schema.
    """

    if not isinstance(raw_response, Mapping):
        return raw_response
    if "item_results" in raw_response:
        return raw_response

    item_statuses = raw_response.get("item_statuses")
    if not isinstance(item_statuses, Mapping):
        return raw_response

    normalized = dict(raw_response)
    normalized["checklist_id"] = normalized.get("checklist_id") or checklist_id
    normalized["worker_id"] = normalized.get("worker_id") or "ui-worker"
    normalized["item_results"] = [
        {
            "checklist_item_id": item_id,
            "status": status,
            "worker_note": normalized.get("note"),
        }
        for item_id, status in item_statuses.items()
    ]
    normalized.pop("item_statuses", None)
    normalized.pop("note", None)
    normalized.setdefault("submitted_at", datetime.now(timezone.utc))
    return normalized
