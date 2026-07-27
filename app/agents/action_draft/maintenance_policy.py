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
_PRIORITY_BY_RISK_LEVEL: dict[RiskLevel, str] = {
    RiskLevel.EMERGENCY: "높음",
    RiskLevel.WARNING: "중간",
    RiskLevel.CAUTION: "낮음",
}


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


def build_maintenance_request_draft(
    *,
    maintenance_request_id: str,
    alert_id: str,
    machine_id: str,
    machine_type: str,
    risk_level: RiskLevel | str | None,
    maintenance_reason: str | None,
    manual_id: str | None,
) -> dict[str, Any]:
    """Compose the worker/manager-facing text for a maintenance-request draft.

    Only formats *why* into a title/recommendation/priority - it does not
    decide whether a draft is needed (`evaluate_maintenance_need` already
    made that call, its output is `maintenance_reason` here).
    """

    reason = maintenance_reason or "반복적인 위험 신호"
    title = f"{machine_id} ({machine_type}) 정비 검토 요청"
    recommendation = f"{reason}(으)로 정비 검토가 필요합니다."
    if manual_id:
        recommendation += f" 관련 SOP: {manual_id}"

    normalized_risk_level = RiskLevel(risk_level) if risk_level else None
    priority = _PRIORITY_BY_RISK_LEVEL.get(normalized_risk_level, "낮음")

    return {
        "maintenance_request_id": maintenance_request_id,
        "alert_id": alert_id,
        "machine_id": machine_id,
        "machine_type": machine_type,
        "title": title,
        "recommendation": recommendation,
        "priority": priority,
    }
