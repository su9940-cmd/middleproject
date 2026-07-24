"""
법률 표현 필터 (FR-15) 및 위험 단계 적합성 확인.

FR-15: "법 위반 필요"와 같은 단정적 표현은 금지되며 "검토 필요" 수준으로만
표현되어야 한다. 이 모듈은 정규 표현식 규칙으로 이 요건을 처리한다.

위험 단계 적합성: 각 조치가 현재 risk_level에 적용 가능한지 확인한다. Action
Draft는 priority만 부여했을 뿐 위험 단계 매칭을 검증하지 않으므로 여기서 확인한다.

원칙:
    - LLM 판정 없음. 결정론적 문자열/집합 연산만 사용.
    - 감사 시 어떤 문구가 걸러졌는지 재현 가능해야 한다.
"""

import re
from typing import Any

from app.core.enums import RiskLevel


# FR-15에서 금지되는 단정 표현 패턴. 대체 문구와 함께 관리한다.
_FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"법\s*위반\s*필요"), "법 위반 여부 검토 필요"),
    (re.compile(r"법률\s*위반\s*필요"), "법률 적용 검토 필요"),
    (re.compile(r"불법\s*행위\s*필요"), "관련 규정 검토 필요"),
    (re.compile(r"위법\s*필요"), "적법 여부 검토 필요"),
    (re.compile(r"과태료\s*필요"), "과태료 대상 여부 검토 필요"),
    (re.compile(r"형사\s*처벌\s*필요"), "관련 규정 확인 필요"),
]

# 위험 단계별로 이 조치가 강제적으로 적용되는 최소 priority.
# 낮은 위험에는 낮은 우선순위 조치까지 포함, 높은 위험에는 높은 우선순위만 남긴다.
_MIN_PRIORITY_BY_RISK: dict[str, int] = {
    RiskLevel.NORMAL: 0,      # 사용되지 않음 (NORMAL이면 Validator까지 오지 않음)
    RiskLevel.CAUTION: 1,     # LOW 이상
    RiskLevel.WARNING: 2,     # MEDIUM 이상
    RiskLevel.EMERGENCY: 2,   # MEDIUM 이상 (HIGH만 남기면 필요 조치가 빠질 수 있음)
}

_PRIORITY_LEVEL: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def sanitize_expression(text: str) -> str:
    """금지 표현을 안전한 대체 표현으로 치환한다.

    치환은 등록된 순서대로 이루어지며, 매칭되지 않으면 원문을 그대로 반환한다.
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _FORBIDDEN_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def contains_forbidden_expression(text: str) -> bool:
    """텍스트에 금지 표현이 남아있는지 확인한다 (감사·테스트용)."""
    if not text:
        return False
    return any(pattern.search(text) for pattern, _ in _FORBIDDEN_PATTERNS)


def sanitize_action(action: dict[str, Any]) -> dict[str, Any]:
    """조치의 title과 description에 법률 표현 필터를 적용한다.

    원본은 수정하지 않고 새 dict를 반환한다.
    """
    cleaned = dict(action)
    cleaned["title"] = sanitize_expression(action.get("title", ""))
    cleaned["description"] = sanitize_expression(action.get("description", ""))
    return cleaned


def find_expression_violations(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return feedback instead of rewriting a worker-facing instruction.

    The final graph requires Validator to return an approved draft unchanged.
    A forbidden expression is therefore fed back to Action Draft for revision,
    rather than silently changing the text at this stage.
    """

    item_id = item.get("checklist_item_id")
    violations: list[dict[str, Any]] = []
    for field in ("title", "instruction"):
        value = str(item.get(field) or "")
        if contains_forbidden_expression(value):
            violations.append(
                {
                    "code": "FORBIDDEN_LEGAL_EXPRESSION",
                    "checklist_item_id": item_id,
                    "field": field,
                    "message": "단정적인 법률 표현을 제거하고 검토 안내 수준으로 수정하세요.",
                }
            )
    return violations


def is_action_appropriate_for_risk(
    action: dict[str, Any],
    risk_level: RiskLevel | str | None,
) -> bool:
    """조치의 priority가 현재 위험 단계에 적합한지 확인한다.

    - required=True 조치는 위험 단계와 무관하게 통과 (안전 우선).
    - 그 외에는 위험 단계별 최소 priority를 만족해야 통과.
    """
    if action.get("required"):
        return True

    action_priority = _PRIORITY_LEVEL.get(str(action.get("priority", "")).upper(), 0)
    min_required = _MIN_PRIORITY_BY_RISK.get(str(risk_level or "").upper(), 0)
    return action_priority >= min_required
