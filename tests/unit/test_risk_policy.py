"""Unit tests for `app.nodes.risk_policy.risk_policy`."""

from __future__ import annotations

from app.core.enums import MachineType, RiskLevel
from app.nodes.risk_policy import risk_policy

_THRESHOLDS = {"caution": 0.145, "warning": 0.29}


def _reading(**overrides) -> dict:
    base = {
        "temperature": 20.0,
        "pressure": 1.0,
        "humidity": 40.0,
        "vibration": 0.1,
        "speed": 1000.0,
        "gas": 0.0,
        "sparks": 0,
    }
    base.update(overrides)
    return base


def _state(ml_risk_score: float, machine_type: MachineType, **reading_overrides) -> dict:
    return {
        "ml_risk_score": ml_risk_score,
        "prediction_thresholds": _THRESHOLDS,
        "machine_type": machine_type,
        "sensor_reading": _reading(**reading_overrides),
    }


def test_below_caution_is_normal():
    result = risk_policy(_state(0.10, MachineType.REACTOR))
    assert result["risk_level"] == RiskLevel.NORMAL
    assert result["emergency_reasons"] == []


def test_between_caution_and_warning_is_caution():
    result = risk_policy(_state(0.20, MachineType.REACTOR))
    assert result["risk_level"] == RiskLevel.CAUTION


def test_at_or_above_warning_is_warning():
    result = risk_policy(_state(0.29, MachineType.REACTOR))
    assert result["risk_level"] == RiskLevel.WARNING


def test_reactor_emergency_rule_overrides_low_ml_score():
    """Emergency physical rules must win even when the ML score alone says NORMAL."""

    result = risk_policy(_state(0.01, MachineType.REACTOR, temperature=43.0))
    assert result["risk_level"] == RiskLevel.EMERGENCY
    assert result["emergency_reasons"]


def test_compressor_emergency_rule():
    result = risk_policy(_state(0.01, MachineType.COMPRESSOR, vibration=5.0))
    assert result["risk_level"] == RiskLevel.EMERGENCY


def test_storage_tank_emergency_rule_requires_both_conditions():
    # gas alone isn't enough - sparks must also cross its threshold.
    result = risk_policy(_state(0.01, MachineType.STORAGE_TANK, gas=9.5, sparks=1))
    assert result["risk_level"] != RiskLevel.EMERGENCY

    result = risk_policy(_state(0.01, MachineType.STORAGE_TANK, gas=9.5, sparks=3))
    assert result["risk_level"] == RiskLevel.EMERGENCY


def test_pump_emergency_rule():
    result = risk_policy(_state(0.01, MachineType.PUMP, vibration=6.0))
    assert result["risk_level"] == RiskLevel.EMERGENCY


def test_policy_version_is_reported():
    result = risk_policy(_state(0.01, MachineType.REACTOR))
    assert result["policy_version"]
