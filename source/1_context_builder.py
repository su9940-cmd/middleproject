# app/agents/memory/context_builder.py — 순수 함수 유틸

# count_unresolved, extract_previous_risk_level, is_risk_escalated, partition_action_ids, collect_previous_titles, compute_repeat_count 6개 함수
# 리포지토리·State·시간에 의존하지 않는 순수 함수만 모아둠
# 왜 분리했나: 로직 오류를 리포지토리 목킹 없이 단독으로 잡을 수 있음. 나중에 조치 판정 규칙이 바뀌어도 여기만 수정하면 됨

"""
Memory Agent의 계산 로직 유틸.

여기 있는 함수는 모두 순수 함수(pure function)로, 리포지토리·State·시간에 의존하지 않는다.
따라서 리포지토리 목킹 없이 단위 테스트가 가능하며, agent.py의 흐름과 독립적으로
로직 오류를 잡을 수 있다.
"""

from typing import Any

from app.core.enums import AlertStatus, RiskLevel


# 위험 상향 감지에 사용되는 순서. 인덱스가 클수록 위험도가 높다.
_RISK_LEVEL_ORDER = [
    RiskLevel.NORMAL,
    RiskLevel.CAUTION,
    RiskLevel.WARNING,
    RiskLevel.EMERGENCY,
]

# 사건이 미해결로 간주되는 경보 상태들.
UNRESOLVED_ALERT_STATUSES: frozenset[str] = frozenset(
    {
        AlertStatus.OPEN,
        AlertStatus.IN_PROGRESS,
        AlertStatus.WAITING_RECHECK,
        AlertStatus.MONITORING,
        AlertStatus.ESCALATED,
    }
)


def count_unresolved(alerts: list[dict[str, Any]]) -> int:
    """미해결로 간주되는 경보 개수를 센다."""
    return sum(1 for alert in alerts if alert.get("alert_status") in UNRESOLVED_ALERT_STATUSES)


def extract_previous_risk_level(alerts: list[dict[str, Any]]) -> str | None:
    """최신순으로 정렬된 경보 목록에서 직전 위험 단계를 뽑는다.

    빈 목록이거나 어떤 경보에도 risk_level 값이 없으면 None을 반환한다.
    """
    for alert in alerts:
        risk = alert.get("risk_level")
        if risk:
            return risk
    return None


def is_risk_escalated(previous: str | None, current: RiskLevel | str | None) -> bool:
    """직전 대비 현재 위험 단계가 상향되었는지 판정한다.

    한쪽이라도 알 수 없는 값이면 False를 반환한다 (보수적 판정).
    """
    if previous is None or current is None:
        return False
    try:
        prev_idx = _RISK_LEVEL_ORDER.index(RiskLevel(previous))
        curr_idx = _RISK_LEVEL_ORDER.index(RiskLevel(current))
    except ValueError:
        return False
    return curr_idx > prev_idx


def partition_action_ids(
    checklist_items: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """체크리스트 항목을 완료/실패 action_id로 분리한다.

    Returns:
        (completed_action_ids, failed_action_ids)
    """
    completed: list[str] = []
    failed: list[str] = []
    for item in checklist_items:
        status = item.get("status")
        action_id = item.get("action_id")
        if not action_id:
            continue
        if status == "COMPLETED":
            completed.append(action_id)
        elif status == "FAILED":
            failed.append(action_id)
    return completed, failed


def collect_previous_titles(checklist_items: list[dict[str, Any]]) -> list[str]:
    """체크리스트 항목의 제목만 순서대로 뽑는다. 제목이 없는 항목은 건너뛴다."""
    return [item["title"] for item in checklist_items if item.get("title")]


def compute_repeat_count(state_repeat_count: int, unresolved_count: int) -> int:
    """State의 repeat_count와 미해결 경보 수 중 큰 값을 채택한다.

    State에 아직 값이 없거나 0인 초기 사건에서도, 미해결 경보가 이미
    누적된 경우 반복 상황을 놓치지 않기 위한 하한선이다.
    """
    return max(state_repeat_count, unresolved_count)
