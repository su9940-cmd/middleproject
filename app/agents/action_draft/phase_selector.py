"""
조치 단계(ActionPhase) 판정.

LLM 미사용 - 순수 규칙 기반. Phase 판정을 결정론적으로 처리하는 것이
감사·테스트에 유리하며, LLM 호출 비용을 줄인다.

우선순위:
    1. risk_level == EMERGENCY               -> EMERGENCY
    2. Memory에서 반복 신호가 감지되면        -> FOLLOW_UP
    3. 그 외                                  -> INITIAL
"""

from typing import Any

from app.core.enums import ActionPhase, RiskLevel


def select_action_phase(
    risk_level: RiskLevel | str | None,
    memory_context: dict[str, Any] | None,
) -> ActionPhase:
    if risk_level == RiskLevel.EMERGENCY:
        return ActionPhase.EMERGENCY

    if memory_context and _has_recurrence_signal(memory_context):
        return ActionPhase.FOLLOW_UP

    return ActionPhase.INITIAL


def _has_recurrence_signal(memory_context: dict[str, Any]) -> bool:
    if memory_context.get("is_repeat_limit_exceeded"):
        return True
    if memory_context.get("is_risk_escalated"):
        return True
    if memory_context.get("unresolved_count", 0) >= 1:
        return True
    return False
