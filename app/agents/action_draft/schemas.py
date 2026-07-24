"""
LLM 구조화 출력 스키마.

안전장치 3: Pydantic 스키마로 LLM 출력을 강제한다. LLM은 자유 양식이 아니라
반드시 이 스키마에 맞는 JSON을 반환해야 한다. 스키마를 벗어난 응답은 파싱
단계에서 거부된다.

action_id, source_ids는 필수 필드이므로 LLM이 누락하면 자동으로 유효성 검사에
실패한다. 이 실패는 draft_composer에서 fallback을 트리거한다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DraftedAction(BaseModel):
    """LLM이 생성하는 단일 조치 항목.

    안전장치 관점:
    - action_id: RAG 문서의 source_id에서 유도해야 함 (draft_composer가 재검증)
    - source_ids: 최소 1개 이상 필수 (근거 없는 조치 방지)
    - title/description: LLM이 RAG 원문에서 인용/요약할 수 있음
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    required: bool
    source_ids: list[str] = Field(min_length=1)
    previously_failed: bool = False

    @field_validator("source_ids")
    @classmethod
    def source_ids_must_not_contain_blanks(cls, value: list[str]) -> list[str]:
        cleaned = [sid for sid in value if sid and sid.strip()]
        if not cleaned:
            raise ValueError("source_ids must contain at least one non-blank id")
        return cleaned


class DraftedChecklist(BaseModel):
    """LLM 응답 전체 구조.

    summary는 참고용이고, actions가 핵심이다. LLM이 actions를 비워 반환하면
    draft_composer가 fallback 경로로 넘어간다.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(max_length=500)
    actions: list[DraftedAction]
