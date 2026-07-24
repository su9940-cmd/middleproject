"""Risk Policy — combines the ML threshold with per-machine emergency rules.

Emergency rules always override the ML-based level (contract section 8).
Thresholds themselves are demo-only, F2-optimized, versioned values — not
legal/safety standards — sourced at runtime from `state["prediction_thresholds"]`
(populated by `predictive_agent` from the trained model's metadata), never
hardcoded here.
"""

from __future__ import annotations

from typing import Any, Callable

from app.core.config import settings
from app.core.enums import MachineType, RiskLevel
from app.graph.state import SafetyState

_EmergencyRuleFn = Callable[[dict[str, Any]], list[str]]


def _reactor_emergency_reasons(reading: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reading["temperature"] >= 42:
        reasons.append(f"REACTOR: temperature {reading['temperature']} >= 42")
    if reading["pressure"] >= 45:
        reasons.append(f"REACTOR: pressure {reading['pressure']} >= 45")
    if reading["gas"] >= 8.5 and reading["sparks"] >= 2:
        reasons.append(
            f"REACTOR: gas {reading['gas']} >= 8.5 and sparks {reading['sparks']} >= 2"
        )
    return reasons


def _compressor_emergency_reasons(reading: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reading["vibration"] >= 4.8:
        reasons.append(f"COMPRESSOR: vibration {reading['vibration']} >= 4.8")
    if reading["speed"] >= 3900:
        reasons.append(f"COMPRESSOR: speed {reading['speed']} >= 3900")
    if reading["pressure"] >= 45:
        reasons.append(f"COMPRESSOR: pressure {reading['pressure']} >= 45")
    return reasons


def _storage_tank_emergency_reasons(reading: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reading["gas"] >= 9 and reading["sparks"] >= 3:
        reasons.append(
            f"STORAGE_TANK: gas {reading['gas']} >= 9 and sparks {reading['sparks']} >= 3"
        )
    if reading["pressure"] >= 45:
        reasons.append(f"STORAGE_TANK: pressure {reading['pressure']} >= 45")
    return reasons


def _pump_emergency_reasons(reading: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reading["vibration"] >= 5.5:
        reasons.append(f"PUMP: vibration {reading['vibration']} >= 5.5")
    if reading["pressure"] <= 10 and reading["vibration"] >= 4.5:
        reasons.append(
            f"PUMP: pressure {reading['pressure']} <= 10 and "
            f"vibration {reading['vibration']} >= 4.5"
        )
    return reasons


_EMERGENCY_RULES: dict[MachineType, _EmergencyRuleFn] = {
    MachineType.REACTOR: _reactor_emergency_reasons,
    MachineType.COMPRESSOR: _compressor_emergency_reasons,
    MachineType.STORAGE_TANK: _storage_tank_emergency_reasons,
    MachineType.PUMP: _pump_emergency_reasons,
}


def _classify_by_ml_score(ml_risk_score: float, thresholds: dict[str, float]) -> RiskLevel:
    if ml_risk_score >= thresholds["warning"]:
        return RiskLevel.WARNING
    if ml_risk_score >= thresholds["caution"]:
        return RiskLevel.CAUTION
    return RiskLevel.NORMAL


def risk_policy(state: SafetyState) -> dict[str, Any]:
    """Classify the current reading into a `RiskLevel`.

    Reads `ml_risk_score`, `prediction_thresholds`, `sensor_reading`,
    `machine_type` from `state`. `machine_profile` is accepted per the
    contract's input list but not yet used — no committed schema defines
    per-machine threshold overrides there yet; flag before relying on it.
    """

    machine_type = state["machine_type"]
    sensor_reading = state["sensor_reading"]

    rule_fn = _EMERGENCY_RULES.get(machine_type)
    emergency_reasons = rule_fn(sensor_reading) if rule_fn else []

    risk_level = _classify_by_ml_score(state["ml_risk_score"], state["prediction_thresholds"])
    if emergency_reasons:
        risk_level = RiskLevel.EMERGENCY

    return {
        "risk_level": risk_level,
        "emergency_reasons": emergency_reasons,
        "policy_version": settings.policy_version,
    }
