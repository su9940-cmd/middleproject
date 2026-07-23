"""Dependency-injected LangGraph assembly for the closed-loop safety flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.predictive import predictive_agent as default_predictive_agent
from app.core.enums import RiskLevel
from app.graph.state import SafetyState
from app.nodes.recovery import recovery_node as default_recovery_node
from app.nodes.risk_policy import risk_policy as default_risk_policy
from app.nodes.worker_interrupt import worker_interrupt as default_worker_interrupt


NodeCallable = Callable[[SafetyState], dict[str, Any]]
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
    worker_interrupt: NodeCallable = default_worker_interrupt


def build_safety_graph(
    dependencies: GraphDependencies,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Compile the final no-middleware safety graph with injected team nodes."""

    builder = StateGraph(SafetyState)

    builder.add_node("predictive_agent", dependencies.predictive_agent)
    builder.add_node("risk_policy", dependencies.risk_policy)
    builder.add_node("recovery_node", dependencies.recovery_node)
    builder.add_node("rag_agent", dependencies.rag_agent)
    builder.add_node("memory_agent", dependencies.memory_agent)
    builder.add_node("action_draft_node", dependencies.action_draft_node)
    builder.add_node("validator_agent", dependencies.validator_agent)
    builder.add_node("send_immediate_alert", dependencies.send_immediate_alert)
    builder.add_node("worker_interrupt", dependencies.worker_interrupt)
    builder.add_node("request_immediate_recheck", dependencies.request_immediate_recheck)

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

    builder.add_edge("recovery_node", END)
    builder.add_edge("send_immediate_alert", END)
    builder.add_edge(["rag_agent", "memory_agent"], "action_draft_node")
    builder.add_edge("action_draft_node", "validator_agent")
    builder.add_edge("validator_agent", "worker_interrupt")
    builder.add_edge("worker_interrupt", "request_immediate_recheck")
    builder.add_edge("request_immediate_recheck", "predictive_agent")

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
    if risk_level is RiskLevel.EMERGENCY:
        return ["send_immediate_alert", "rag_agent", "memory_agent"]
    return ["rag_agent", "memory_agent"]
