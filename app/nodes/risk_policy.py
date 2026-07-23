"""Deterministic ML-threshold and machine emergency policy evaluation."""

from __future__ import annotations

from math import isfinite
from typing import Any, Callable

from app.core.enums import MachineType, RiskLevel
from app.core.exceptions import RiskPolicyError
from app.graph.state import SafetyState


POLICY_VERSION = "demo-risk-policy-v1"

EmergencyRule = Callable[[dict[str, Any]], str | None]


def _at_least(sensor: dict[str, Any], field: str, limit: float, code: str) -> str | None:
    value = float(sensor[field])
    if value >= limit:
        return f"{code}: {field}={value:g} >= {limit:g}"
    return None


def _reactor_gas_and_sparks(sensor: dict[str, Any]) -> str | None:
    gas = float(sensor["gas"])
    sparks = int(sensor["sparks"])
    if gas >= 8.5 and sparks >= 2:
        return f"REACTOR_GAS_SPARKS: gas={gas:g} >= 8.5 and sparks={sparks} >= 2"
    return None


def _storage_gas_and_sparks(sensor: dict[str, Any]) -> str | None:
    gas = float(sensor["gas"])
    sparks = int(sensor["sparks"])
    if gas >= 9.0 and sparks >= 3:
        return f"STORAGE_GAS_SPARKS: gas={gas:g} >= 9 and sparks={sparks} >= 3"
    return None


def _pump_low_pressure_vibration(sensor: dict[str, Any]) -> str | None:
    pressure = float(sensor["pressure"])
    vibration = float(sensor["vibration"])
    if pressure <= 10.0 and vibration >= 4.5:
        return (
            "PUMP_LOW_PRESSURE_VIBRATION: "
            f"pressure={pressure:g} <= 10 and vibration={vibration:g} >= 4.5"
        )
    return None


EMERGENCY_RULES: dict[MachineType, tuple[EmergencyRule, ...]] = {
    MachineType.REACTOR: (
        lambda sensor: _at_least(sensor, "temperature", 42.0, "REACTOR_TEMP_HIGH"),
        lambda sensor: _at_least(sensor, "pressure", 45.0, "REACTOR_PRESSURE_HIGH"),
        _reactor_gas_and_sparks,
    ),
    MachineType.COMPRESSOR: (
        lambda sensor: _at_least(sensor, "vibration", 4.8, "COMPRESSOR_VIBRATION_HIGH"),
        lambda sensor: _at_least(sensor, "speed", 3900.0, "COMPRESSOR_SPEED_HIGH"),
        lambda sensor: _at_least(sensor, "pressure", 45.0, "COMPRESSOR_PRESSURE_HIGH"),
    ),
    MachineType.STORAGE_TANK: (
        _storage_gas_and_sparks,
        lambda sensor: _at_least(sensor, "pressure", 45.0, "STORAGE_PRESSURE_HIGH"),
    ),
    MachineType.PUMP: (
        lambda sensor: _at_least(sensor, "vibration", 5.5, "PUMP_VIBRATION_HIGH"),
        _pump_low_pressure_vibration,
    ),
}


def risk_policy(state: SafetyState) -> dict[str, Any]:
    """Combine ML thresholds with machine-specific emergency overrides."""

    try:
        score, caution, warning, machine_type, sensor = _validated_inputs(state)
        emergency_reasons = [
            reason
            for rule in EMERGENCY_RULES[machine_type]
            if (reason := rule(sensor)) is not None
        ]

        if emergency_reasons:
            risk_level = RiskLevel.EMERGENCY
        elif score >= warning:
            risk_level = RiskLevel.WARNING
        elif score >= caution:
            risk_level = RiskLevel.CAUTION
        else:
            risk_level = RiskLevel.NORMAL
    except Exception as exc:
        error = exc if isinstance(exc, RiskPolicyError) else RiskPolicyError(str(exc))
        return {
            "error_code": error.error_code,
            "error_message": str(error),
            "failed_node": "risk_policy",
        }

    return {
        "risk_level": risk_level,
        "emergency_reasons": emergency_reasons,
        "policy_version": POLICY_VERSION,
        "error_code": None,
        "error_message": None,
        "failed_node": None,
    }


def _validated_inputs(
    state: SafetyState,
) -> tuple[float, float, float, MachineType, dict[str, Any]]:
    try:
        score = float(state["ml_risk_score"])
        thresholds = state["prediction_thresholds"]
        caution = float(thresholds["caution"])
        warning = float(thresholds["warning"])
        machine_type = MachineType(state["machine_type"])
        sensor = state["sensor_reading"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RiskPolicyError(f"invalid or missing policy input: {exc}") from exc

    if not all(isfinite(value) for value in (score, caution, warning)):
        raise RiskPolicyError("risk score and thresholds must be finite")
    if not 0.0 <= score <= 1.0:
        raise RiskPolicyError("ml_risk_score must be between 0 and 1")
    if not 0.0 <= caution <= warning <= 1.0:
        raise RiskPolicyError("thresholds must satisfy 0 <= caution <= warning <= 1")
    if not isinstance(sensor, dict):
        raise RiskPolicyError("sensor_reading must be a dictionary")

    required_fields = {
        MachineType.REACTOR: {"temperature", "pressure", "gas", "sparks"},
        MachineType.COMPRESSOR: {"vibration", "speed", "pressure"},
        MachineType.STORAGE_TANK: {"gas", "sparks", "pressure"},
        MachineType.PUMP: {"vibration", "pressure"},
    }[machine_type]
    missing = sorted(required_fields - sensor.keys())
    if missing:
        raise RiskPolicyError(f"sensor_reading is missing emergency fields: {', '.join(missing)}")

    return score, caution, warning, machine_type, sensor
