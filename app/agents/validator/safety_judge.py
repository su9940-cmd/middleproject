"""
LLM 안전성 판정기 (Safety Judge).

역할:
    LLM에게 최종 체크리스트가 산업안전 관점에서 문제 없는지 판정을 받는다.
    LLM은 조치를 수정·삭제하지 않으며, "이 조치에 이런 우려가 있다"는
    참고 판정만 반환한다.

안전 원칙:
    - LLM 실패 또는 스키마 위반 시 조치는 그대로 통과 (안전한 기본 동작)
    - 실패 시 safety_review에 "판정 불가" 상태를 표시하여 사후 확인 가능
    - overall_verdict가 UNSAFE여도 Validator가 조치를 제거하지 않음
      (판정은 사람이 참고, 최종 결정은 Worker Interrupt에서 사람이)
"""

import json
from typing import Any

from pydantic import ValidationError

from app.agents.validator.schemas import SafetyReview
from app.core.enums import RiskLevel

# Action Draft와 동일한 LLMClient Protocol을 재사용한다.
# 실제 인스턴스는 D가 별도로 주입하므로 다른 모델을 쓸 수 있다.
from app.agents.action_draft.llm_client import LLMClient


_SYSTEM_PROMPT = """\
당신은 산업안전 체크리스트 감사 보조자입니다. 다음 원칙을 지키세요.

원칙:
1. 체크리스트를 수정하거나 재작성하지 마세요. 오직 판정만 하세요.
2. 각 조치에 대해 산업안전 관점에서 우려되는 점만 표시하세요.
3. 새로운 조치를 제안하지 마세요.
4. 판정은 SAFE, REVIEW_NEEDED, UNSAFE 중 하나로 요약하세요.
5. "법 위반 필요"와 같은 단정 표현을 사용하지 마세요.

출력은 지정된 JSON 스키마를 정확히 따라야 합니다.
"""


def judge_safety(
    llm: LLMClient | None,
    actions: list[dict[str, Any]],
    risk_level: RiskLevel | str,
    machine_type: str | None,
) -> dict[str, Any]:
    """LLM에게 안전성 판정을 받는다.

    Args:
        llm: LLM 클라이언트. None이면 판정을 건너뛰고 SKIPPED 상태를 반환.
        actions: 규칙 검증을 이미 통과한 최종 조치 목록.
        risk_level: 현재 위험 단계.
        machine_type: 설비 타입 (프롬프트 컨텍스트용).

    Returns:
        safety_review dict. LLM 실패 시에도 dict 구조를 유지한다.
    """
    if llm is None or not actions:
        return _skipped_review("LLM 미주입 또는 판정할 조치 없음")

    user_prompt = _build_prompt(actions, risk_level, machine_type)

    try:
        raw = llm.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=SafetyReview,
        )
        review = SafetyReview.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        return _failed_review(str(exc))

    # 알려진 action_id만 남기고, 나머지 concerns는 제거 (LLM 환각 방지)
    known_ids = {a["action_id"] for a in actions}
    valid_concerns = [
        {"action_id": c.action_id, "severity": c.severity, "reason": c.reason}
        for c in review.concerns
        if c.action_id in known_ids
    ]

    return {
        "status": "COMPLETED",
        "overall_verdict": review.overall_verdict,
        "concerns": valid_concerns,
        "notes": review.notes,
    }


def _skipped_review(reason: str) -> dict[str, Any]:
    return {
        "status": "SKIPPED",
        "overall_verdict": "SAFE",  # 판정 없음은 통과로 간주 (안전한 기본값)
        "concerns": [],
        "notes": reason,
    }


def _failed_review(error: str) -> dict[str, Any]:
    """LLM 판정 실패 시. 조치는 그대로 통과시키는 상태를 명시적으로 남긴다."""
    return {
        "status": "FAILED",
        "overall_verdict": "REVIEW_NEEDED",  # 판정 실패 시 사람 확인 유도
        "concerns": [],
        "notes": f"LLM 안전성 판정 실패: {error}",
    }


def _build_prompt(
    actions: list[dict[str, Any]],
    risk_level: RiskLevel | str,
    machine_type: str | None,
) -> str:
    parts: list[str] = []
    parts.append(f"[현재 위험 단계] {risk_level}")
    if machine_type:
        parts.append(f"[설비 타입] {machine_type}")

    parts.append("[검토 대상 조치 목록]")
    for i, action in enumerate(actions, start=1):
        parts.append(
            f"({i}) action_id={action['action_id']}, "
            f"priority={action.get('priority', '?')}, "
            f"required={action.get('required', False)}, "
            f"previously_failed={action.get('previously_failed', False)}\n"
            f"    title: {action.get('title', '')}\n"
            f"    description: {action.get('description', '')}\n"
            f"    source_ids: {', '.join(action.get('source_ids', []))}"
        )

    parts.append(
        "\n각 조치에 대해 산업안전 관점의 우려 사항이 있으면 concerns에 담고, "
        "전체 판정을 overall_verdict로 요약하세요. 조치를 수정하거나 삭제하지 마세요."
    )
    return "\n".join(parts)
