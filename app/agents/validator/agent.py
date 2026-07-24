"""Validator node for grounded, worker-ready checklists.

The Validator never rewrites checklist instructions.  It either passes the
Action Draft through with its identifiers and citations intact, or returns
structured feedback so that Action Draft can create a revised version.
"""

from __future__ import annotations

from typing import Any

from app.agents.action_draft.llm_client import LLMClient
from app.agents.validator.deduplicator import deduplicate_items
from app.agents.validator.expression_filter import find_expression_violations
from app.agents.validator.safety_judge import judge_safety
from app.agents.validator.source_grounding import filter_grounded_items
from app.core.exceptions import ChecklistValidationError
from app.graph.state import SafetyState


class ValidatorAgent:
    """Validate an Action Draft without changing worker-facing instructions."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client

    def __call__(self, state: SafetyState) -> dict[str, Any]:
        action_draft = state.get("action_draft")
        risk_level = state.get("risk_level")
        if not isinstance(action_draft, dict):
            raise ChecklistValidationError(
                "action_draft is required to validate a checklist",
                details={"failed_node": "validator_agent"},
            )
        if risk_level is None:
            raise ChecklistValidationError(
                "risk_level is required to validate a checklist",
                details={"failed_node": "validator_agent"},
            )

        feedback = self._collect_feedback(
            action_draft=action_draft,
            documents=state.get("retrieved_documents") or [],
        )
        attempts = int(state.get("validation_attempts") or 0)
        if feedback:
            return {
                "validation_status": "REVISE",
                "validation_feedback": feedback,
                "validation_attempts": attempts + 1,
            }

        # LLM feedback is advisory only: deterministic source and expression
        # checks decide whether a draft can be passed to a worker.
        safety_review = judge_safety(
            llm=self._llm,
            items=action_draft["items"],
            risk_level=risk_level,
            machine_type=state.get("machine_type"),
        )
        final_checklist = dict(action_draft)
        final_checklist["safety_review"] = safety_review
        return {
            "final_checklist": final_checklist,
            "validation_status": "PASSED",
            "validation_feedback": [],
            "validation_attempts": attempts,
        }

    def _collect_feedback(
        self,
        *,
        action_draft: dict[str, Any],
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        feedback: list[dict[str, Any]] = []
        checklist_id = action_draft.get("checklist_id")
        items = action_draft.get("items")
        if not isinstance(checklist_id, str) or not checklist_id.strip():
            feedback.append({"code": "MISSING_CHECKLIST_ID", "message": "checklist_id is required"})
        if not isinstance(items, list) or not items:
            feedback.append({"code": "EMPTY_CHECKLIST", "message": "at least one checklist item is required"})
            return feedback

        grounded, dropped = filter_grounded_items(items, documents)
        if dropped:
            feedback.extend(dropped)
        deduplicated = deduplicate_items(grounded)
        if len(deduplicated) != len(grounded):
            feedback.append({
                "code": "DUPLICATE_ITEM",
                "message": "duplicate checklist items must be merged by Action Draft",
            })
        for item in grounded:
            feedback.extend(find_expression_violations(item))
        return feedback
