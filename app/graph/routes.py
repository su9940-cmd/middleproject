"""Stable conditional-edge labels for the safety graph."""

from app.core.enums import RiskLevel
from app.graph.state import SafetyState


def route_by_risk(state: SafetyState) -> str:
    """Route NORMAL, EMERGENCY, and other abnormal states."""

    risk_level = RiskLevel(state["risk_level"])
    if risk_level is RiskLevel.NORMAL:
        return "normal"
    if risk_level is RiskLevel.EMERGENCY:
        return "emergency"
    return "abnormal"
