"""
LLM 안전성 판정 스키마.

LLM은 이 스키마 그대로 JSON을 반환해야 한다. 자유 양식 금지.

판정만 담고 조치를 수정·재작성하지 않는다:
    - overall_verdict: 전체 체크리스트가 안전한가
    - concerns: 우려 항목만 표시 (제거 X, 수정 X)
    - notes: 감사·작업자 참고용 요약

Validator는 이 결과를 조치에 반영하지 않고 final_checklist의 메타 필드로 첨부한다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SafetyConcern(BaseModel):
    """개별 조치에 대한 우려 사항. 조치를 제거하거나 수정하지 않는다."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: str = Field(min_length=1)
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    reason: str = Field(min_length=1, max_length=500)


class SafetyReview(BaseModel):
    """LLM 안전성 판정 결과 전체."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    overall_verdict: Literal["SAFE", "REVIEW_NEEDED", "UNSAFE"]
    concerns: list[SafetyConcern] = Field(default_factory=list)
    notes: str = Field(default="", max_length=1000)
