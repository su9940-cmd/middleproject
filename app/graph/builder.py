"""Dependency-injected LangGraph assembly for the closed-loop safety flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.predictive import predictive_agent as default_predictive_agent
from app.agents.action_draft import ActionDraftAgent
from app.agents.validator import ValidatorAgent
from app.agents.rag import rag_agent as default_rag_agent
from app.core.enums import RiskLevel
from app.core.exceptions import (
    ChecklistValidationError,
    MemoryLookupError,
    RAGRetrievalError,
)
from app.graph.state import SafetyState
from app.nodes.recovery import recovery_node as default_recovery_node
from app.nodes.risk_policy import risk_policy as default_risk_policy
from app.nodes.worker_interrupt import worker_interrupt as default_worker_interrupt
from app.nodes.immediate_recheck import request_immediate_recheck as default_recheck_node
from app.nodes.notification import send_immediate_alert as default_notification_node
from app.nodes.alert_lifecycle import alert_lifecycle_node as default_alert_lifecycle_node


NodeCallable = Callable[[SafetyState], dict[str, Any]]
MAX_VALIDATION_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class GraphDependencies:
    """Node implementations supplied by each project role."""

    rag_agent: NodeCallable
    memory_agent: NodeCallable
    action_draft_node: NodeCallable
    validator_agent: NodeCallable
    send_immediate_alert: NodeCallable
    request_immediate_recheck: NodeCallable

    predictive_agent: NodeCallable = default_predictive_agent
    risk_policy: NodeCallable = default_risk_policy
    recovery_node: NodeCallable = default_recovery_node
    alert_lifecycle_node: NodeCallable = default_alert_lifecycle_node
    worker_interrupt: NodeCallable = default_worker_interrupt


class _FallbackLLMClient:
    """Deliberately unavailable LLM so Action Draft uses its grounded fallback.

    The demo must remain runnable without an API key.  Action Draft already
    converts provider failures into an SOP-grounded deterministic checklist.
    A real LLM client can be injected through ``GraphDependencies`` later.
    """

    def generate_structured(self, **_: Any) -> str:
        raise RuntimeError("no LLM client configured")


def _default_memory_agent(state: SafetyState) -> dict[str, Any]:
    """Return an empty, valid memory context for the standalone API demo.

    Database persistence is handled by the backend repositories.  Until a
    synchronous graph repository adapter is configured, this conservative
    context prevents fabricated historical decisions while keeping the graph
    runnable.  Production wiring should replace it via ``GraphDependencies``.
    """

    return {
        "memory_context": {
            "previous_alert_count": 0,
            "unresolved_count": 0,
            "previous_risk_level": None,
            "previous_checklist_items": [],
            "completed_action_ids": [],
            "failed_action_ids": [],
            "latest_worker_note": None,
            "maintenance_history": [],
            "repeat_count": int(state.get("repeat_count") or 0),
            "is_risk_escalated": False,
            "is_repeat_limit_exceeded": False,
        }
    }


def default_graph_dependencies(*, use_database_memory: bool = False) -> GraphDependencies:
    """Build runnable default dependencies for the local FastAPI demo."""

    memory_node = _default_memory_agent
    if use_database_memory:
        from app.agents.memory.backend_adapter import backend_memory_agent

        async def memory_node(state: SafetyState) -> dict[str, Any]:
            try:
                return await backend_memory_agent(state)
            except Exception as exc:
                return {
                    "error_code": MemoryLookupError.error_code,
                    "error_message": str(exc),
                    "failed_node": "memory_agent",
                }

    return GraphDependencies(
        rag_agent=default_rag_agent,
        memory_agent=memory_node,
        action_draft_node=ActionDraftAgent(_FallbackLLMClient()),
        validator_agent=ValidatorAgent(),
        send_immediate_alert=default_notification_node,
        request_immediate_recheck=default_recheck_node,
    )


def build_safety_graph(
    dependencies: GraphDependencies | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the final no-middleware safety graph with injected team nodes."""

    dependencies = dependencies or default_graph_dependencies()
    builder = StateGraph(SafetyState)

    builder.add_node("predictive_agent", dependencies.predictive_agent)
    builder.add_node("risk_policy", dependencies.risk_policy)
    builder.add_node("recovery_node", dependencies.recovery_node)
    builder.add_node("alert_lifecycle_node", dependencies.alert_lifecycle_node)
    builder.add_node("rag_agent", dependencies.rag_agent)
    builder.add_node("memory_agent", dependencies.memory_agent)
    builder.add_node("context_guard", _context_guard)
    builder.add_node("action_draft_node", dependencies.action_draft_node)
    builder.add_node("validator_agent", dependencies.validator_agent)
    builder.add_node("send_immediate_alert", dependencies.send_immediate_alert)
    builder.add_node("worker_interrupt", dependencies.worker_interrupt, defer=True)
    builder.add_node("request_immediate_recheck", dependencies.request_immediate_recheck)
    builder.add_node("checklist_validation_failure", _checklist_validation_failure)

    builder.add_edge(START, "predictive_agent")
    builder.add_conditional_edges(
        "predictive_agent",
        _route_after_predictive,
        {"continue": "risk_policy", "error": END},
    )
    builder.add_conditional_edges(
        "risk_policy",
        _route_after_risk_policy,
    )
    builder.add_conditional_edges(
        "alert_lifecycle_node",
        _route_after_alert_lifecycle,
    )

    builder.add_edge("recovery_node", END)
    builder.add_edge(["rag_agent", "memory_agent"], "context_guard")
    builder.add_conditional_edges(
        "context_guard",
        _route_after_context,
        {"continue": "action_draft_node", "error": END},
    )
    builder.add_edge("action_draft_node", "validator_agent")
    builder.add_conditional_edges(
        "validator_agent",
        _route_after_validator,
        {
            "passed": "worker_interrupt",
            "revise": "action_draft_node",
            "error": "checklist_validation_failure",
        },
    )
    builder.add_edge("checklist_validation_failure", END)
    builder.add_edge("send_immediate_alert", "worker_interrupt")
    builder.add_edge("worker_interrupt", "request_immediate_recheck")
    # The next sensor reading starts a fresh graph invocation on the same
    # thread.  Do not loop on the stale reading inside this run.
    builder.add_edge("request_immediate_recheck", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def graph_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Build the required LangGraph invocation config for one incident thread."""

    normalized = thread_id.strip()
    if not normalized:
        raise ValueError("thread_id must not be empty")
    return {"configurable": {"thread_id": normalized}}


def _route_after_predictive(state: SafetyState) -> Literal["continue", "error"]:
    return "error" if state.get("error_code") else "continue"


def _route_after_risk_policy(state: SafetyState) -> list[str]:
    """Fan out context nodes and the direct emergency alert branch."""

    if state.get("error_code"):
        return [END]
    risk_level = RiskLevel(state["risk_level"])
    if risk_level is RiskLevel.NORMAL:
        return ["recovery_node"]
    return ["alert_lifecycle_node"]


def _route_after_alert_lifecycle(state: SafetyState) -> list[str]:
    """Fan out RAG/Memory and emergency pre-notification after alert state."""

    if state.get("error_code"):
        return [END]
    if RiskLevel(state["risk_level"]) is RiskLevel.EMERGENCY:
        return ["send_immediate_alert", "rag_agent", "memory_agent"]
    return ["rag_agent", "memory_agent"]


def _context_guard(state: SafetyState) -> dict[str, Any]:
    """Fan-in barrier used before Action Draft consumes RAG and Memory."""

    if state.get("error_code"):
        return {}
    documents = state.get("retrieved_documents")
    if not isinstance(documents, list) or not documents:
        return {
            "error_code": RAGRetrievalError.error_code,
            "error_message": "RAG returned no documents",
            "failed_node": "rag_agent",
        }
    if not isinstance(state.get("memory_context"), dict):
        return {
            "error_code": MemoryLookupError.error_code,
            "error_message": "Memory Agent returned no context",
            "failed_node": "memory_agent",
        }
    return {}


def _route_after_context(state: SafetyState) -> Literal["continue", "error"]:
    if state.get("error_code"):
        return "error"
    return "continue"


def _route_after_validator(
    state: SafetyState,
) -> Literal["passed", "revise", "error"]:
    """Pass a grounded checklist or loop structured feedback to Action Draft.

    Validators written before the feedback contract may omit
    ``validation_status`` and return only ``final_checklist``; that shape is
    treated as passed for backward compatibility during team integration.
    """

    if state.get("error_code"):
        return "error"

    status = str(state.get("validation_status") or "").strip().upper()
    if status == "PASSED" or (not status and state.get("final_checklist")):
        return "passed"
    if status == "REVISE":
        attempts = int(state.get("validation_attempts") or 0)
        return "revise" if attempts < MAX_VALIDATION_ATTEMPTS else "error"
    return "error"


def _checklist_validation_failure(state: SafetyState) -> dict[str, Any]:
    """Record a stable failure when Validator cannot approve a safe draft."""

    attempts = int(state.get("validation_attempts") or 0)
    return {
        "error_code": ChecklistValidationError.error_code,
        "error_message": (
            "checklist validation failed"
            f" after {attempts} revision attempt(s)"
        ),
        "failed_node": "validator_agent",
    }
