"""Deterministic validation of Action Draft citations (AC-04)."""

from __future__ import annotations

from typing import Any


def filter_grounded_items(
    items: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition items by whether every citation maps to this RAG result.

    Action Draft stores a citation as a source id, document type, section and
    exact excerpt.  Checking all of these prevents a valid-but-unrelated
    ``source_id`` from being used as a superficial citation.
    """

    grounded: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []
    for item in items:
        error = _grounding_error(item, documents)
        if error is None:
            grounded.append(item)
        else:
            feedback.append(error)
    return grounded, feedback


def _grounding_error(
    item: dict[str, Any], documents: list[dict[str, Any]]
) -> dict[str, Any] | None:
    item_id = item.get("checklist_item_id")
    if not isinstance(item_id, str) or not item_id.strip():
        return {"code": "MISSING_ITEM_ID", "message": "checklist_item_id is required"}

    citations = item.get("citations")
    if not isinstance(citations, list) or not citations:
        return _feedback(item_id, "MISSING_CITATION", "each item requires at least one SOP citation")

    has_sop = False
    for citation in citations:
        if not isinstance(citation, dict):
            return _feedback(item_id, "INVALID_CITATION", "citation must be an object")
        if _matches_retrieved_document(citation, documents):
            if str(citation.get("document_type") or "").lower() == "sop":
                has_sop = True
            continue
        return _feedback(
            item_id,
            "UNGROUNDED_CITATION",
            "citation does not match a document retrieved for this incident",
        )
    if not has_sop:
        return _feedback(item_id, "MISSING_SOP_CITATION", "worker actions must be grounded in SOP")
    return None


def _matches_retrieved_document(citation: dict[str, Any], documents: list[dict[str, Any]]) -> bool:
    source_id = str(citation.get("source_id") or "").strip()
    excerpt = str(citation.get("source_excerpt") or "").strip()
    if not source_id or not excerpt:
        return False
    citation_type = str(citation.get("document_type") or "").strip().lower()
    citation_section = str(citation.get("section") or "").strip()
    for document in documents:
        if str(document.get("source_id") or "").strip() != source_id:
            continue
        if str(document.get("document_type") or "").strip().lower() != citation_type:
            continue
        if str(document.get("section") or "").strip() != citation_section:
            continue
        content = str(document.get("content") or "").strip()
        if excerpt == content:
            return True
    return False


def _feedback(item_id: str, code: str, message: str) -> dict[str, Any]:
    return {"code": code, "checklist_item_id": item_id, "message": message}


# Backward-compatible names used by the original Validator unit tests.
def collect_valid_source_ids(documents: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(str(doc.get("source_id")) for doc in documents if doc.get("source_id"))


def is_action_grounded(action: dict[str, Any], valid_source_ids: frozenset[str]) -> bool:
    source_ids = action.get("source_ids") or []
    return bool(source_ids) and all(source_id in valid_source_ids for source_id in source_ids)


def filter_grounded_actions(
    actions: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid_source_ids = collect_valid_source_ids(documents)
    return (
        [action for action in actions if is_action_grounded(action, valid_source_ids)],
        [action for action in actions if not is_action_grounded(action, valid_source_ids)],
    )
