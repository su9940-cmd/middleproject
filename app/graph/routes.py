"""Conditional-edge routing helpers for the safety graph."""

from __future__ import annotations

from app.core.enums import RiskLevel
from app.graph.state import SafetyState


def route_by_risk(state: SafetyState) -> str:
    """Classify `state["risk_level"]` into `"normal" | "abnormal" | "emergency"`."""

    risk_level = state["risk_level"]

    if risk_level == RiskLevel.NORMAL:
        return "normal"

    if risk_level == RiskLevel.EMERGENCY:
        return "emergency"

    return "abnormal"
