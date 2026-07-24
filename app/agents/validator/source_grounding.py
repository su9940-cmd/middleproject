"""
근거 검증 (AC-04).

Validator가 통과시키는 모든 체크리스트 항목은 반드시 RAG가 실제로 반환한
문서의 source_id에 매핑되어야 한다. 이 모듈은 순수 함수로 그 매핑을 검사한다.

Action Draft 단계에서 source_id 없는 문서는 이미 제외되지만, Validator는
다시 두 가지를 재검증한다:
    1. action.source_ids가 비어있지 않은가
    2. 각 source_id가 이번 사건의 retrieved_documents에 실제로 존재하는가

이 재검증이 필요한 이유: Action Draft 이후에 상태가 조작되었거나,
전달 과정에서 source_id가 잘못될 경우를 감지하기 위함.
"""

from typing import Any


def collect_valid_source_ids(documents: list[dict[str, Any]]) -> frozenset[str]:
    """RAG가 반환한 문서 목록에서 유효한 source_id 집합을 만든다."""
    return frozenset(
        doc["source_id"]
        for doc in documents
        if doc.get("source_id")
    )


def is_action_grounded(
    action: dict[str, Any],
    valid_source_ids: frozenset[str],
) -> bool:
    """action의 모든 source_id가 유효한 문서에 매핑되는지 확인한다.

    - source_ids가 비어있으면 근거 없음(False).
    - source_ids 중 하나라도 valid_source_ids에 없으면 근거 없음(False).
    - 모든 source_id가 매핑되면 근거 있음(True).
    """
    source_ids = action.get("source_ids") or []
    if not source_ids:
        return False
    return all(sid in valid_source_ids for sid in source_ids)


def filter_grounded_actions(
    actions: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """근거 있는 조치와 없는 조치를 분리한다.

    Returns:
        (grounded_actions, dropped_actions)
        dropped_actions는 Validator가 fallback을 결정할 때 참고한다.
    """
    valid_ids = collect_valid_source_ids(documents)
    grounded: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for action in actions:
        if is_action_grounded(action, valid_ids):
            grounded.append(action)
        else:
            dropped.append(action)
    return grounded, dropped
