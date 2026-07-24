"""
Action Draft Agent (LLM 기반).

RAG와 Memory 병렬 결과를 받아 LLM으로 조치 초안을 조립한다.
Phase 판정과 정비 판정은 결정론성을 위해 규칙 기반으로 유지한다.

역할:
    - 조치 단계(ActionPhase) 결정 (규칙)
    - LLM으로 RAG 문서 근거 기반 조치 후보 생성 (안전장치 4개 적용)
    - 정비 요청 필요 여부 판정 (규칙)
    - 합의된 스키마(action_phase/summary/actions/maintenance_reason/escalation_reason) 조립

구성 규약:
    - 클래스 + LLM 클라이언트 생성자 주입
    - LangGraph 노드 진입점은 __call__(state)
    - 성공 시 {"action_draft": ..., "requires_maintenance_request": ...}
    - 실패 시 ActionDraftError raise (재시도는 상위 계층)
    - LLM 실패는 fallback으로 대응하며 예외로 격상하지 않음 (FR-09 원칙)

Validator 재작성 루프는 되지 않는다. Validator가 문제를 발견하면 그 자리에서
필터링/fallback으로 처리한다.
"""

from typing import Any

from app.agents.action_draft.draft_composer import compose_llm_draft
from app.agents.action_draft.llm_client import LLMClient
from app.agents.action_draft.maintenance_policy import evaluate_maintenance_need
from app.agents.action_draft.phase_selector import select_action_phase
from app.core.enums import ActionPhase, RiskLevel
from app.core.exceptions import ActionDraftError
from app.graph.state import SafetyState


class ActionDraftAgent:
    """LangGraph의 action_draft 노드.

        agent = ActionDraftAgent(llm_client=my_llm)
        graph.add_node("action_draft", agent)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def __call__(self, state: SafetyState) -> dict[str, Any]:
        risk_level = state.get("risk_level")
        if risk_level is None:
            raise ActionDraftError(
                "risk_level is required to build an action draft",
                details={"failed_node": "action_draft"},
            )

        documents = state.get("retrieved_documents") or []
        memory_context = state.get("memory_context") or {}
        emergency_reasons = state.get("emergency_reasons") or []

        try:
            draft, requires_maintenance = self._build_draft(
                risk_level=risk_level,
                documents=documents,
                memory_context=memory_context,
                emergency_reasons=emergency_reasons,
            )
        except ActionDraftError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ActionDraftError(
                f"failed to build action draft: {exc}",
                details={"failed_node": "action_draft"},
            ) from exc

        return {
            "action_draft": draft,
            "requires_maintenance_request": requires_maintenance,
        }

    def _build_draft(
        self,
        risk_level: RiskLevel | str,
        documents: list[dict[str, Any]],
        memory_context: dict[str, Any],
        emergency_reasons: list[str],
    ) -> tuple[dict[str, Any], bool]:
        phase = select_action_phase(risk_level, memory_context)

        # LLM으로 조치 후보 생성 (실패 시 fallback으로 규칙 기반 조립)
        actions, llm_summary, used_fallback = compose_llm_draft(
            llm=self._llm,
            documents=documents,
            memory_context=memory_context,
            risk_level=risk_level,
            emergency_reasons=emergency_reasons,
        )

        requires_maintenance, maintenance_reason = evaluate_maintenance_need(
            risk_level, memory_context
        )

        summary = _compose_summary(
            phase=phase,
            risk_level=risk_level,
            memory_context=memory_context,
            action_count=len(actions),
            llm_summary=llm_summary,
            used_fallback=used_fallback,
        )
        escalation_reason = _compose_escalation_reason(
            phase, risk_level, memory_context, emergency_reasons
        )

        draft = {
            "action_phase": phase,
            "summary": summary,
            "actions": actions,
            "maintenance_reason": maintenance_reason,
            "escalation_reason": escalation_reason,
            "used_llm_fallback": used_fallback,
        }
        return draft, requires_maintenance


def _compose_summary(
    phase: ActionPhase,
    risk_level: RiskLevel | str,
    memory_context: dict[str, Any],
    action_count: int,
    llm_summary: str,
    used_fallback: bool,
) -> str:
    """summary는 LLM이 만든 요약을 우선 사용하고, 규칙 기반 메타 정보를 덧붙인다."""
    meta_parts = [f"위험 단계 {risk_level}", f"조치 단계 {phase}"]
    if memory_context.get("unresolved_count"):
        meta_parts.append(f"미해결 경보 {memory_context['unresolved_count']}건")
    if memory_context.get("is_repeat_limit_exceeded"):
        meta_parts.append("반복 임계값 초과")
    meta_parts.append(f"신규 조치 {action_count}건")
    if used_fallback:
        meta_parts.append("fallback 사용")

    meta = ", ".join(meta_parts)
    if llm_summary and not used_fallback:
        return f"{llm_summary} ({meta})"
    return meta


def _compose_escalation_reason(
    phase: ActionPhase,
    risk_level: RiskLevel | str,
    memory_context: dict[str, Any],
    emergency_reasons: list[str],
) -> str | None:
    if phase == ActionPhase.INITIAL:
        return None

    if phase == ActionPhase.EMERGENCY:
        if emergency_reasons:
            return "긴급 규칙 충족: " + ", ".join(emergency_reasons)
        return f"긴급 위험 단계 감지: {risk_level}"

    reasons: list[str] = []
    if memory_context.get("is_repeat_limit_exceeded"):
        reasons.append("반복 임계값 초과")
    if memory_context.get("is_risk_escalated"):
        prev = memory_context.get("previous_risk_level")
        reasons.append(f"이전 {prev} → 현재 {risk_level} 상향")
    unresolved = memory_context.get("unresolved_count", 0)
    if unresolved:
        reasons.append(f"미해결 경보 {unresolved}건 존재")
    return ", ".join(reasons) if reasons else "반복 상황 감지"
