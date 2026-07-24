"""LangGraph wiring for the SafetyState closed-loop graph (CLAUDE.md section 9).

Owned by role D (ML / orchestration / git-master). `predictive_agent`,
`risk_policy`, and `recovery_node` are D's own real implementations.
`alert_lifecycle_node` is an 11th node not in the original design (see its
own docstring) added to fill a real gap: nothing owned `alert_status`
transitions on the abnormal/emergency path. Every other node in the 10-node
design is owned by role A, B, or C and imported from its contractually-fixed
module path (see `_EXTERNAL_NODES`); until that role's file lands, a local
stub stands in so the graph still compiles and the NORMAL path is testable
end-to-end today. The stub is replaced automatically the moment the real
module/function shows up — nothing here needs to change when that happens.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib import import_module
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.predictive import predictive_agent
from app.core.exceptions import ApplicationError
from app.graph.checkpoints import get_checkpointer
from app.graph.routes import route_by_risk
from app.graph.state import SafetyState
from app.nodes.alert_lifecycle import alert_lifecycle_node
from app.nodes.recovery import recovery_node
from app.nodes.risk_policy import risk_policy

logger = logging.getLogger(__name__)

NodeFn = Callable[[SafetyState], Any]

# (module_path, function_name) for every node this role doesn't own.
_EXTERNAL_NODES: dict[str, tuple[str, str]] = {
    "rag_agent": ("app.agents.rag", "rag_agent"),
    "memory_agent": ("app.agents.memory", "memory_agent"),
    "action_draft_node": ("app.nodes.action_draft", "action_draft_node"),
    "validator_agent": ("app.agents.validator", "validator_agent"),
    "send_immediate_alert": ("app.nodes.notification", "send_immediate_alert"),
    "worker_interrupt": ("app.nodes.worker_interrupt", "worker_interrupt"),
    "request_immediate_recheck": ("app.nodes.immediate_recheck", "request_immediate_recheck"),
}


def _stub(node_name: str) -> NodeFn:
    """Placeholder for a node another role owns but hasn't landed yet."""

    def _not_implemented(state: SafetyState) -> dict[str, Any]:
        module_path, attr_name = _EXTERNAL_NODES[node_name]
        raise NotImplementedError(
            f"'{node_name}' isn't implemented yet - add {attr_name}() to {module_path}"
        )

    return _not_implemented


def _resolve_node(node_name: str) -> NodeFn:
    """Import an externally-owned node, falling back to a stub if it's missing."""

    module_path, attr_name = _EXTERNAL_NODES[node_name]
    try:
        module = import_module(module_path)
        return getattr(module, attr_name)
    except (ImportError, AttributeError):
        logger.warning("%s not found at %s.%s yet, using a stub", node_name, module_path, attr_name)
        return _stub(node_name)


def _with_error_handling(node_name: str, node_fn: NodeFn) -> NodeFn:
    """Wrap a node so a raised `ApplicationError` becomes the shared error-field contract.

    A node that returns its own dedicated failure fields instead of raising
    (e.g. `send_immediate_alert`'s `NotificationStatus.FAILED` branch) is
    unaffected — this only catches actual exceptions.

    Also a safety net: if an earlier node in this run already set
    `error_code`, skip calling the real node entirely and return `{}`. Most
    nodes assume their upstream fields exist (e.g. `risk_policy` reads
    `state["ml_risk_score"]` directly) and would raise an unrelated
    `KeyError` instead of the original error if allowed to run on a
    already-failed state - see the two explicit routing guards below for the
    two spots that would otherwise KeyError today.
    """

    def _wrapped(state: SafetyState) -> dict[str, Any]:
        if state.get("error_code"):
            return {}
        try:
            return node_fn(state)
        except ApplicationError as exc:
            logger.error("node %s failed: %s", node_name, exc)
            return {
                "error_code": exc.error_code,
                "error_message": str(exc),
                "failed_node": node_name,
            }

    return _wrapped


def _route_after_predictive(state: SafetyState) -> str:
    """Stop the run if `predictive_agent` failed, instead of letting `risk_policy`
    crash on the `ml_risk_score`/`prediction_thresholds` it never got."""

    return END if state.get("error_code") else "risk_policy"


def _dispatch_from_risk_policy(state: SafetyState) -> list[str]:
    """Fan out from `risk_policy` per `route_by_risk`'s 3-way classification.

    NORMAL -> recovery_node (closes/silences the alert). CAUTION/WARNING/
    EMERGENCY -> alert_lifecycle_node first (opens/reopens/escalates the
    alert before anything downstream reads `alert_status`). Stops the run
    instead if `risk_policy` itself failed (no `risk_level` to route on).
    """

    if state.get("error_code"):
        return [END]

    branch = route_by_risk(state)
    if branch == "normal":
        return ["recovery_node"]
    return ["alert_lifecycle_node"]


def _dispatch_from_alert_lifecycle(state: SafetyState) -> list[str]:
    """Fan out from `alert_lifecycle_node` per the same classification.

    CAUTION/WARNING -> rag_agent + memory_agent in parallel. EMERGENCY ->
    those two AND send_immediate_alert, all three at once - the alert
    doesn't block checklist generation (contract section 9).
    """

    if state.get("error_code"):
        return [END]

    if route_by_risk(state) == "emergency":
        return ["send_immediate_alert", "rag_agent", "memory_agent"]
    return ["rag_agent", "memory_agent"]


def build_safety_graph() -> CompiledStateGraph:
    """Assemble and compile the closed-loop safety graph."""

    graph = StateGraph(SafetyState)

    graph.add_node("predictive_agent", _with_error_handling("predictive_agent", predictive_agent))
    graph.add_node("risk_policy", _with_error_handling("risk_policy", risk_policy))
    graph.add_node("recovery_node", _with_error_handling("recovery_node", recovery_node))
    graph.add_node(
        "alert_lifecycle_node", _with_error_handling("alert_lifecycle_node", alert_lifecycle_node)
    )

    for node_name in _EXTERNAL_NODES:
        # worker_interrupt joins two paths of different lengths (the 1-hop
        # emergency pre-notification and the 3-hop RAG/Memory->Action
        # Draft->Validator checklist chain) — defer=True makes it wait for
        # every predecessor in flight before running, instead of firing
        # once per path.
        graph.add_node(
            node_name,
            _with_error_handling(node_name, _resolve_node(node_name)),
            defer=(node_name == "worker_interrupt"),
        )

    graph.set_entry_point("predictive_agent")
    graph.add_conditional_edges("predictive_agent", _route_after_predictive)
    graph.add_conditional_edges("risk_policy", _dispatch_from_risk_policy)
    graph.add_conditional_edges("alert_lifecycle_node", _dispatch_from_alert_lifecycle)
    graph.add_edge("recovery_node", END)

    # RAG || Memory fan-out -> Action Draft fan-in (shared by abnormal + emergency).
    graph.add_edge("rag_agent", "action_draft_node")
    graph.add_edge("memory_agent", "action_draft_node")
    graph.add_edge("action_draft_node", "validator_agent")

    # Emergency pre-notification rejoins the checklist chain at worker_interrupt.
    graph.add_edge("send_immediate_alert", "worker_interrupt")
    graph.add_edge("validator_agent", "worker_interrupt")

    # Resume after the worker submits -> request an immediate recheck, then
    # stop this run (WAITING_RECHECK). There's no real IoT sensor yet - we
    # stand in for it by manually submitting the recheck reading through the
    # same sensor-ingest entry point used for every other reading. So the new
    # data isn't available inside this run at all; the loop back to
    # predictive_agent happens when that manual submission triggers a fresh
    # `graph.invoke({..., "measurement_mode": IMMEDIATE_RECHECK, "sensor_reading": ...},
    # config={"configurable": {"thread_id": thread_id}})` on the same thread_id -
    # predictive_agent is the entry point, and the checkpointer carries the
    # rest of this thread's state forward into that new run.
    graph.add_edge("worker_interrupt", "request_immediate_recheck")
    graph.add_edge("request_immediate_recheck", END)

    return graph.compile(checkpointer=get_checkpointer())
