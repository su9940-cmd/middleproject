"""context_builder의 순수 함수 단위 테스트.

리포지토리·State가 필요 없는 로직만 검증한다.
"""

import pytest

from app.agents.memory.context_builder import (
    collect_previous_titles,
    compute_repeat_count,
    count_unresolved,
    extract_previous_risk_level,
    is_risk_escalated,
    partition_action_ids,
)
from app.core.enums import AlertStatus, RiskLevel


# ---------------------------------------------------------------------------
# count_unresolved
# ---------------------------------------------------------------------------

def test_count_unresolved_ignores_resolved_and_none():
    alerts = [
        {"alert_status": AlertStatus.OPEN},
        {"alert_status": AlertStatus.RESOLVED},
        {"alert_status": AlertStatus.MONITORING},
        {"alert_status": AlertStatus.NONE},
        {},  # 상태 필드 없음
    ]
    assert count_unresolved(alerts) == 2


def test_count_unresolved_on_empty_list():
    assert count_unresolved([]) == 0


# ---------------------------------------------------------------------------
# extract_previous_risk_level
# ---------------------------------------------------------------------------

def test_extract_previous_risk_level_returns_first_available():
    alerts = [
        {"risk_level": "WARNING"},
        {"risk_level": "CAUTION"},
    ]
    assert extract_previous_risk_level(alerts) == "WARNING"


def test_extract_previous_risk_level_skips_empty_and_returns_next():
    alerts = [
        {},
        {"risk_level": None},
        {"risk_level": "CAUTION"},
    ]
    assert extract_previous_risk_level(alerts) == "CAUTION"


def test_extract_previous_risk_level_none_when_absent():
    assert extract_previous_risk_level([]) is None
    assert extract_previous_risk_level([{"risk_level": None}]) is None


# ---------------------------------------------------------------------------
# is_risk_escalated
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "previous,current,expected",
    [
        ("CAUTION", RiskLevel.EMERGENCY, True),
        ("WARNING", RiskLevel.EMERGENCY, True),
        ("NORMAL", RiskLevel.CAUTION, True),
        ("WARNING", RiskLevel.CAUTION, False),
        ("EMERGENCY", RiskLevel.EMERGENCY, False),
        (None, RiskLevel.EMERGENCY, False),
        ("CAUTION", None, False),
        ("INVALID", RiskLevel.EMERGENCY, False),
    ],
)
def test_is_risk_escalated(previous, current, expected):
    assert is_risk_escalated(previous, current) is expected


# ---------------------------------------------------------------------------
# partition_action_ids
# ---------------------------------------------------------------------------

def test_partition_action_ids_splits_and_ignores_missing_ids():
    items = [
        {"action_id": "A1", "status": "COMPLETED"},
        {"action_id": "A2", "status": "FAILED"},
        {"action_id": "A3", "status": "PENDING"},
        {"action_id": None, "status": "COMPLETED"},  # 무시
        {"status": "COMPLETED"},  # 무시
    ]
    completed, failed = partition_action_ids(items)
    assert completed == ["A1"]
    assert failed == ["A2"]


def test_partition_action_ids_preserves_input_order():
    items = [
        {"action_id": "A1", "status": "COMPLETED"},
        {"action_id": "A2", "status": "COMPLETED"},
        {"action_id": "A3", "status": "COMPLETED"},
    ]
    completed, _ = partition_action_ids(items)
    assert completed == ["A1", "A2", "A3"]


# ---------------------------------------------------------------------------
# collect_previous_titles
# ---------------------------------------------------------------------------

def test_collect_previous_titles_skips_missing_titles():
    items = [
        {"title": "밸브 점검"},
        {"title": ""},
        {"title": None},
        {},
        {"title": "온도 확인"},
    ]
    assert collect_previous_titles(items) == ["밸브 점검", "온도 확인"]


# ---------------------------------------------------------------------------
# compute_repeat_count
# ---------------------------------------------------------------------------

def test_compute_repeat_count_takes_max():
    assert compute_repeat_count(state_repeat_count=1, unresolved_count=3) == 3
    assert compute_repeat_count(state_repeat_count=5, unresolved_count=2) == 5
    assert compute_repeat_count(state_repeat_count=0, unresolved_count=0) == 0
