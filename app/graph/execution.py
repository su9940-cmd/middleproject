"""Public helpers for starting and resuming incident graphs."""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.types import Command
from pydantic_core import to_jsonable_python

from app.graph.builder import graph_config
from app.graph.state import SafetyState
from app.models.worker import WorkerResumePayload


def start_incident(graph: Any, state: SafetyState, *, thread_id: str) -> dict[str, Any]:
    """Start or continue an incident graph using a stable thread identifier."""

    return graph.invoke(to_jsonable_python(state), config=graph_config(thread_id))


def resume_worker_interrupt(
    graph: Any,
    response: WorkerResumePayload | Mapping[str, Any],
    *,
    thread_id: str,
) -> dict[str, Any]:
    """Resume a worker-interrupted graph with a validated response payload."""

    validated = (
        response
        if isinstance(response, WorkerResumePayload)
        else WorkerResumePayload.model_validate(dict(response))
    )
    return graph.invoke(
        Command(resume=validated.model_dump(mode="json")),
        config=graph_config(thread_id),
    )
