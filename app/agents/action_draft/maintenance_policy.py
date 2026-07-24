"""
정비 요청 필요 여부 판정.

LLM 미사용 - 순수 규칙 기반. 합의된 규칙:
    1) 반복 3회 이상 (Memory의 is_repeat_limit_exceeded)
    2) 긴급 상태 (risk_level == EMERGENCY)
    3) 경고 이상으로 상향된 이력 (is_risk_escalated + current >= WARNING)

차단 조건: 진행 중 정비 요청이 있으면 중복 생성하지 않는다.
"""

from typing import Any

from app.core.enums import RiskLevel


_WARNING_OR_ABOVE: frozenset[str] = frozenset({RiskLevel.WARNING, RiskLevel.EMERGENCY})
_ACTIVE_MAINTENANCE_STATUSES: frozenset[str] = frozenset({"PENDING", "APPROVED", "IN_PROGRESS"})


def evaluate_maintenance_need(
    risk_level: RiskLevel | str | None,
    memory_context: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    context = memory_context or {}

    if _has_active_maintenance(context):
        return False, None

    reasons: list[str] = []

    if context.get("is_repeat_limit_exceeded"):
        reasons.append("반복 3회 이상")

    if risk_level == RiskLevel.EMERGENCY:
        reasons.append("긴급 상태")

    if context.get("is_risk_escalated") and str(risk_level or "").upper() in _WARNING_OR_ABOVE:
        reasons.append("경고 이상으로 상향된 이력")

    if not reasons:
        return False, None

    return True, ", ".join(reasons)


def _has_active_maintenance(memory_context: dict[str, Any]) -> bool:
    for record in memory_context.get("maintenance_history", []) or []:
        if record.get("approval_status") in _ACTIVE_MAINTENANCE_STATUSES:
            return True
    return False
