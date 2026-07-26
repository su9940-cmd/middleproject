"""Unit tests for `app.graph.routes.route_by_risk`."""

from __future__ import annotations

from app.core.enums import RiskLevel
from app.graph.routes import route_by_risk


def test_normal_routes_to_normal():
    assert route_by_risk({"risk_level": RiskLevel.NORMAL}) == "normal"


def test_caution_routes_to_abnormal():
    assert route_by_risk({"risk_level": RiskLevel.CAUTION}) == "abnormal"


def test_warning_routes_to_abnormal():
    assert route_by_risk({"risk_level": RiskLevel.WARNING}) == "abnormal"


def test_emergency_routes_to_emergency():
    assert route_by_risk({"risk_level": RiskLevel.EMERGENCY}) == "emergency"
