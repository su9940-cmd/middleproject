"""Action Draft Agent.

RAG documents and Memory context are converted into a final-checklist-shaped
draft. The Validator may pass that draft through unchanged or return structured
feedback; on a revision pass this node consumes the feedback and previous draft
to produce a new version.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.action_draft.draft_composer import compose_llm_draft
from app.agents.action_draft.llm_client import LLMClient
from app.agents.action_draft.maintenance_policy import evaluate_maintenance_need
from app.agents.action_draft.phase_selector import select_action_phase
from app.core.enums import ActionPhase, RiskLevel
from app.core.exceptions import ActionDraftError
from app.graph.state import SafetyState


class ActionDraftAgent:
    """LangGraph node that returns ``action_draft`` and maintenance intent."""

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
        if not documents:
            raise ActionDraftError(
                "retrieved_documents must not be empty for an abnormal alert",
                details={"failed_node": "action_draft"},
            )

        memory_context = state.get("memory_context") or {}
        validation_feedback = state.get("validation_feedback") or []
        validation_attempts = int(state.get("validation_attempts") or 0)

        try:
            draft, requires_maintenance = self._build_draft(
                state=state,
                risk_level=risk_level,
                documents=documents,
                memory_context=memory_context,
                emergency_reasons=state.get("emergency_reasons") or [],
                validation_feedback=validation_feedback,
                validation_attempts=validation_attempts,
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
        *,
        state: SafetyState,
        risk_level: RiskLevel | str,
        documents: list[dict[str, Any]],
        memory_context: dict[str, Any],
        emergency_reasons: list[str],
        validation_feedback: list[dict[str, Any]],
        validation_attempts: int,
    ) -> tuple[dict[str, Any], bool]:
        phase = select_action_phase(risk_level, memory_context)

        items, llm_summary, used_fallback, supporting_references = compose_llm_draft(
            llm=self._llm,
            documents=documents,
            memory_context=memory_context,
            risk_level=risk_level,
            emergency_reasons=emergency_reasons,
            machine_id=state.get("machine_id"),
            machine_type=state.get("machine_type"),
            sensor_reading=state.get("sensor_reading") or {},
            ml_risk_score=state.get("ml_risk_score"),
            risk_evidence=state.get("risk_evidence") or [],
            validation_feedback=validation_feedback,
            previous_draft=state.get("action_draft"),
            validation_attempts=validation_attempts,
        )
        if not items:
            raise ActionDraftError(
                "no grounded SOP checklist items could be composed",
                details={
                    "failed_node": "action_draft",
                    "document_count": len(documents),
                    "validation_attempts": validation_attempts,
                },
            )

        requires_maintenance, maintenance_reason = evaluate_maintenance_need(
            risk_level, memory_context
        )

        summary = _compose_summary(
            phase=phase,
            risk_level=risk_level,
            memory_context=memory_context,
            item_count=len(items),
            llm_summary=llm_summary,
            used_fallback=used_fallback,
        )
        escalation_reason = _compose_escalation_reason(
            phase, risk_level, memory_context, emergency_reasons
        )
        version = validation_attempts + 1
        checklist_id = _build_checklist_id(
            alert_id=state.get("alert_id"),
            machine_id=state.get("machine_id"),
            version=version,
        )
        machine_profile = state.get("machine_profile") or {}
        sop_citations = [
            citation
            for item in items
            for citation in item.get("citations", [])
            if citation.get("document_type") == "sop"
        ]
        manual_id = state.get("manual_id") or (
            sop_citations[0].get("source_id") if sop_citations else None
        )
        manual_version = machine_profile.get("manual_version") or next(
            (
                citation.get("manual_version")
                for citation in sop_citations
                if citation.get("manual_version")
            ),
            None,
        )

        draft = {
            "checklist_id": checklist_id,
            "alert_id": state.get("alert_id"),
            "version": version,
            "action_phase": phase,
            "risk_level": str(risk_level),
            "summary": summary,
            "items": items,
            "supporting_references": supporting_references,
            "manual_id": manual_id,
            "manual_version": manual_version,
            "maintenance_reason": maintenance_reason,
            "escalation_reason": escalation_reason,
            "requires_manager_report": phase in {
                ActionPhase.FOLLOW_UP,
                ActionPhase.EMERGENCY,
            },
            "requires_maintenance_request": requires_maintenance,
            "used_llm_fallback": used_fallback,
            "validation_attempts": validation_attempts,
        }
        return draft, requires_maintenance


def _build_checklist_id(
    *, alert_id: str | None, machine_id: str | None, version: int
) -> str:
    identity = alert_id or machine_id or "UNKNOWN"
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", identity).strip("-") or "UNKNOWN"
    return f"CL-{normalized}-V{version}"


def _compose_summary(
    *,
    phase: ActionPhase,
    risk_level: RiskLevel | str,
    memory_context: dict[str, Any],
    item_count: int,
    llm_summary: str,
    used_fallback: bool,
) -> str:
    meta_parts = [f"위험 단계 {risk_level}", f"조치 단계 {phase}"]
    if memory_context.get("unresolved_count"):
        meta_parts.append(f"미해결 경보 {memory_context['unresolved_count']}건")
    if memory_context.get("is_repeat_limit_exceeded"):
        meta_parts.append("반복 임계값 초과")
    meta_parts.append(f"조치 {item_count}건")
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
        previous = memory_context.get("previous_risk_level")
        reasons.append(f"이전 {previous} → 현재 {risk_level} 상향")
    unresolved = memory_context.get("unresolved_count", 0)
    if unresolved:
        reasons.append(f"미해결 경보 {unresolved}건 존재")
    return ", ".join(reasons) if reasons else "반복 상황 감지"
