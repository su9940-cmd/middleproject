"""
LLM 기반 조치 초안 조립기.

안전장치 4개를 모두 여기에 적용한다:
    1. RAG 원문을 벗어난 창작 금지 - source_ids가 실제 문서에 존재하는지 재검증
    2. source_id 가드 - 스키마와 재검증으로 이중 확인
    3. Pydantic 구조화 출력 강제 - 스키마 파싱 실패 시 조치 제외
    4. 결정론성 확보 - LLM 클라이언트 구현체가 temperature=0 유지 (프로토콜 계약)

LLM이 반환한 조치 중:
    - 스키마를 위반한 항목: 파싱 단계에서 자동 제거
    - source_id가 RAG 문서에 없는 항목: 근거 없음으로 제거 (안전장치 1)
    - 완료된 조치와 중복: memory_context 기반으로 제거
    - 실패했던 조치: previously_failed=True 플래그 강제 갱신
"""

import json
from typing import Any

from pydantic import ValidationError

from app.agents.action_draft.llm_client import LLMClient
from app.agents.action_draft.schemas import DraftedChecklist
from app.core.enums import RiskLevel


_SYSTEM_PROMPT = """\
당신은 산업안전 체크리스트 초안 작성 보조자입니다. 다음 원칙을 반드시 지키세요.

원칙:
1. 제공된 문서(RAG 결과)의 내용을 근거로만 조치를 작성하세요.
2. 문서에 없는 절차나 규정을 임의로 만들지 마세요.
3. 각 조치의 source_ids에는 반드시 실제로 참고한 문서의 source_id만 넣으세요.
4. "베스트 프랙티스"와 같은 단정적 표현을 사용하지 마세요. "검토 필요"로 완화하세요.
5. 이미 완료된 조치(completed_action_ids)는 다시 포함하지 마세요.
6. 과거 실패한 조치(failed_action_ids)는 previously_failed=true로 표시하세요.

출력은 지정된 JSON 스키마를 정확히 따라야 합니다.
"""


def compose_llm_draft(
    llm: LLMClient,
    documents: list[dict[str, Any]],
    memory_context: dict[str, Any],
    risk_level: RiskLevel | str,
    emergency_reasons: list[str],
) -> tuple[list[dict[str, Any]], str, bool]:
    """LLM으로 조치 초안을 만들고 안전장치를 적용한다.

    Returns:
        (actions, summary, used_fallback)
        used_fallback=True는 LLM 실패로 규칙 기반 fallback을 사용했음을 의미한다.
    """
    valid_source_ids = _collect_source_ids(documents)

    user_prompt = _build_user_prompt(
        documents=documents,
        memory_context=memory_context,
        risk_level=risk_level,
        emergency_reasons=emergency_reasons,
    )

    try:
        raw_response = llm.generate_structured(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=DraftedChecklist,
        )
        parsed = DraftedChecklist.model_validate(json.loads(raw_response))
    except (json.JSONDecodeError, ValidationError, Exception):
        # LLM 호출 실패 또는 스키마 위반 - fallback으로 규칙 기반 조립
        fallback_actions = _fallback_from_documents(
            documents, memory_context, valid_source_ids, risk_level
        )
        return fallback_actions, "LLM 응답 실패 - RAG 원문 기반 fallback", True

    filtered_actions = _apply_safety_guards(
        parsed.actions,
        valid_source_ids=valid_source_ids,
        memory_context=memory_context,
    )

    # LLM이 정상 응답했지만 안전장치 통과 후 조치가 하나도 남지 않은 경우
    if not filtered_actions:
        fallback_actions = _fallback_from_documents(
            documents, memory_context, valid_source_ids, risk_level
        )
        return fallback_actions, "LLM 조치가 근거 검증에서 모두 제외됨 - fallback", True

    return filtered_actions, parsed.summary, False


def _collect_source_ids(documents: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(
        doc["source_id"] for doc in documents if doc.get("source_id")
    )


def _apply_safety_guards(
    llm_actions: list,
    valid_source_ids: frozenset[str],
    memory_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """LLM 조치에 안전장치 1, 2를 적용한다.

    - source_ids 중 하나라도 유효하지 않으면 조치 제외 (창작 방지)
    - 이미 완료된 action_id는 제외
    - failed_action_ids는 previously_failed=True 강제
    """
    completed = set(memory_context.get("completed_action_ids") or [])
    failed = set(memory_context.get("failed_action_ids") or [])

    result: list[dict[str, Any]] = []
    for action in llm_actions:
        # 안전장치 1: 모든 source_id가 실제 문서에 존재해야 함
        if not all(sid in valid_source_ids for sid in action.source_ids):
            continue

        if action.action_id in completed:
            continue

        result.append(
            {
                "action_id": action.action_id,
                "title": action.title,
                "description": action.description,
                "priority": action.priority,
                "required": action.required,
                "source_ids": list(action.source_ids),
                # LLM이 놓치더라도 서버측에서 강제
                "previously_failed": bool(action.previously_failed) or action.action_id in failed,
            }
        )

    return result


def _fallback_from_documents(
    documents: list[dict[str, Any]],
    memory_context: dict[str, Any],
    valid_source_ids: frozenset[str],
    risk_level: RiskLevel | str,
) -> list[dict[str, Any]]:
    """LLM 실패 시 RAG 원문을 그대로 조치로 변환한다 (규칙 기반 fallback).

    이 fallback은 FR-09 원칙(재시도 없음)을 지키면서도 작업자에게 최소한의
    근거 문서를 노출한다. Validator는 이 fallback 조치도 정상 조치로 처리한다.
    """
    completed = set(memory_context.get("completed_action_ids") or [])
    failed = set(memory_context.get("failed_action_ids") or [])
    default_priority = "HIGH" if str(risk_level or "").upper() in {"EMERGENCY", "WARNING"} else "MEDIUM"

    seen: set[str] = set()
    actions: list[dict[str, Any]] = []

    for doc in documents:
        source_id = doc.get("source_id")
        if not source_id or source_id not in valid_source_ids:
            continue

        action_id = source_id
        section = doc.get("section")
        if section:
            action_id = f"{source_id}#{section}"

        if action_id in seen or action_id in completed:
            continue
        seen.add(action_id)

        actions.append(
            {
                "action_id": action_id,
                "title": doc.get("title") or "제목 없음",
                "description": doc.get("content") or "",
                "priority": default_priority,
                "required": doc.get("document_type") in {"SOP", "LAW", "KOSHA"},
                "source_ids": [source_id],
                "previously_failed": action_id in failed,
            }
        )

    return actions


def _build_user_prompt(
    documents: list[dict[str, Any]],
    memory_context: dict[str, Any],
    risk_level: RiskLevel | str,
    emergency_reasons: list[str],
) -> str:
    """LLM에 전달할 사용자 프롬프트를 구성한다.

    각 문서·이력 정보를 명확히 라벨링하여 LLM이 실수로 다른 정보를 근거로
    삼지 않도록 한다.
    """
    parts: list[str] = []
    parts.append(f"[현재 위험 단계] {risk_level}")

    if emergency_reasons:
        parts.append(f"[긴급 사유] {', '.join(emergency_reasons)}")

    completed = memory_context.get("completed_action_ids") or []
    failed = memory_context.get("failed_action_ids") or []
    if completed:
        parts.append(f"[이미 완료된 조치 ID] {', '.join(completed)}")
    if failed:
        parts.append(f"[과거 실패한 조치 ID] {', '.join(failed)}")

    if memory_context.get("latest_worker_note"):
        parts.append(f"[최근 작업자 메모] {memory_context['latest_worker_note']}")

    parts.append("[근거 문서]")
    for i, doc in enumerate(documents, start=1):
        if not doc.get("source_id"):
            continue
        parts.append(
            f"({i}) source_id={doc['source_id']}, "
            f"type={doc.get('document_type', '?')}, "
            f"title={doc.get('title', '?')}\n"
            f"    content={doc.get('content', '')}"
        )

    parts.append("\n위 문서만 근거로 삼아 조치 목록을 JSON으로 반환하세요.")
    return "\n".join(parts)
