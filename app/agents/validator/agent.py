"""
Validator Agent (FR-09, FR-15, AC-04).

하이브리드 구조:
    - 조치 결정(통과/제외)은 규칙 기반 (source_id 검증, 중복 병합, 위험 적합성, 법률 표현)
    - 안전성 판정은 LLM (참고용, 조치를 수정·삭제하지 않음)

LLM 사용 방식:
    - LLMClient는 생성자로 주입 (선택 사항, None이면 판정 건너뜀)
    - LLM은 "이 체크리스트가 안전한가"만 판정
    - overall_verdict가 UNSAFE여도 조치는 제거되지 않음
      (판정 결과는 사람이 참고, 최종 결정은 Worker Interrupt)

FR-09 준수:
    - 재시도 분기 없음
    - LLM 판정 실패 시 조치는 통과, safety_review에 FAILED 상태 표시
    - Action Draft로 되돌리는 재작성 요청 없음
"""

from typing import Any

from app.agents.action_draft.llm_client import LLMClient
from app.agents.validator.deduplicator import deduplicate_actions
from app.agents.validator.expression_filter import (
    is_action_appropriate_for_risk,
    sanitize_action,
    sanitize_expression,
)
from app.agents.validator.safety_judge import judge_safety
from app.agents.validator.source_grounding import filter_grounded_actions
from app.core.enums import RiskLevel
from app.core.exceptions import ChecklistValidationError
from app.graph.state import SafetyState


class ValidatorAgent:
    """LangGraph의 validator_agent 노드.

        agent = ValidatorAgent(llm_client=llm)  # LLM 있으면 안전성 판정 수행
        agent = ValidatorAgent()                # LLM 없으면 규칙 기반만 수행
        graph.add_node("validator_agent", agent)
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    def __call__(self, state: SafetyState) -> dict[str, Any]:
        risk_level = state.get("risk_level")
        action_draft = state.get("action_draft")
        documents = state.get("retrieved_documents") or []

        if risk_level is None:
            raise ChecklistValidationError(
                "risk_level is required to validate a checklist",
                details={"failed_node": "validator_agent"},
            )
        if not action_draft:
            raise ChecklistValidationError(
                "action_draft is required to validate a checklist",
                details={"failed_node": "validator_agent"},
            )

        try:
            final_checklist = self._build_final_checklist(
                action_draft=action_draft,
                documents=documents,
                risk_level=risk_level,
                machine_type=state.get("machine_type"),
                alert_id=state.get("alert_id"),
            )
        except ChecklistValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ChecklistValidationError(
                f"failed to validate checklist: {exc}",
                details={"failed_node": "validator_agent"},
            ) from exc

        return {"final_checklist": final_checklist}

    # ------------------------------------------------------------------
    # 6단계 파이프라인
    # ------------------------------------------------------------------

    def _build_final_checklist(
        self,
        action_draft: dict[str, Any],
        documents: list[dict[str, Any]],
        risk_level: RiskLevel | str,
        machine_type: str | None,
        alert_id: str | None,
    ) -> dict[str, Any]:
        raw_actions = action_draft.get("actions") or []

        # 1) 근거 검증 (AC-04)
        grounded, dropped = filter_grounded_actions(raw_actions, documents)

        # 2) 중복 병합
        deduped = deduplicate_actions(grounded)

        # 3) 위험 적합성 확인
        appropriate = [
            action for action in deduped
            if is_action_appropriate_for_risk(action, risk_level)
        ]

        # 4) 법률 표현 필터 (FR-15)
        sanitized = [sanitize_action(action) for action in appropriate]

        # 5) LLM 안전성 판정 (참고용, 조치 수정 X)
        safety_review = judge_safety(
            llm=self._llm,
            actions=sanitized,
            risk_level=risk_level,
            machine_type=machine_type,
        )

        # 6) 최종 조립
        return self._compose_final_checklist(
            actions=sanitized,
            dropped=dropped,
            safety_review=safety_review,
            action_draft=action_draft,
            alert_id=alert_id,
        )

    def _compose_final_checklist(
        self,
        actions: list[dict[str, Any]],
        dropped: list[dict[str, Any]],
        safety_review: dict[str, Any],
        action_draft: dict[str, Any],
        alert_id: str | None,
    ) -> dict[str, Any]:
        """최종 dict 조립. actions가 비면 fallback으로 전환."""
        if not actions:
            return {
                "alert_id": alert_id,
                "actions": [],
                "final_status": "READY_WITH_FALLBACK",
                "fallback_reason": (
                    "근거 기반 조치를 확정하지 못했습니다. 원문 SOP를 직접 확인하세요."
                ),
                "dropped_action_count": len(dropped),
                "raw_summary": sanitize_expression(action_draft.get("summary", "")),
                "safety_review": safety_review,
            }

        return {
            "alert_id": alert_id,
            "actions": actions,
            "final_status": "READY_FOR_WORKER",
            "dropped_action_count": len(dropped),
            "safety_review": safety_review,
        }
