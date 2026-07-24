"""
중복 조치 병합.

Action Draft가 이미 action_id 단위로 중복 제거를 했지만, Validator는
다음 두 경우까지 추가로 병합한다:

    1. action_id가 서로 다르지만 정규화된 title이 동일한 경우
       (예: SOP와 KOSHA가 같은 조치를 다른 문서에서 정의)
    2. source_ids만 다른 동일 조치

병합 원칙:
    - source_ids는 합집합으로 보존한다 (근거 추적 강화)
    - priority는 더 높은 것을 채택 (HIGH > MEDIUM > LOW)
    - required는 하나라도 True면 True
    - previously_failed는 하나라도 True면 True (안전 우선)
    - title, description은 먼저 등장한 조치의 것을 유지
"""

import re
from typing import Any


_PRIORITY_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """공백·대소문자·특수문자를 제거한 정규화 키를 만든다."""
    stripped = _WHITESPACE_RE.sub("", (title or "").casefold())
    return "".join(ch for ch in stripped if ch.isalnum())


def deduplicate_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """정규화된 title 기준으로 중복 조치를 병합한다.

    입력 순서는 보존한다 - 먼저 등장한 조치의 title/description을 대표로 사용.
    """
    merged_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for action in actions:
        key = normalize_title(action.get("title", ""))
        if not key:
            # 정규화 후 비면 병합 대상이 아님 - 그대로 보존
            key = f"__no_key__{id(action)}"

        if key not in merged_by_key:
            merged_by_key[key] = dict(action)
            merged_by_key[key]["source_ids"] = list(action.get("source_ids") or [])
            order.append(key)
        else:
            merged_by_key[key] = _merge_action(merged_by_key[key], action)

    return [merged_by_key[k] for k in order]


def deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one representative for exact worker-facing duplicate items.

    Unlike the legacy action format, an Action Draft item has ``instruction``
    and citation objects.  Title-only merging is unsafe because two SOP steps
    can have the same short title but different instructions.  Validator only
    detects duplicate drafts; it does not mutate or merge them for the worker.
    """

    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (
            normalize_title(str(item.get("title") or "")),
            _WHITESPACE_RE.sub(" ", str(item.get("instruction") or "").strip()).casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _merge_action(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """두 조치를 하나로 병합한다. base가 대표, other의 속성은 합집합·상향."""
    merged = dict(base)

    # source_ids는 합집합 (순서 보존)
    seen = set(merged.get("source_ids") or [])
    combined = list(merged.get("source_ids") or [])
    for sid in other.get("source_ids") or []:
        if sid not in seen:
            combined.append(sid)
            seen.add(sid)
    merged["source_ids"] = combined

    # priority는 더 높은 것
    base_p = _PRIORITY_ORDER.get(str(merged.get("priority", "")).upper(), 0)
    other_p = _PRIORITY_ORDER.get(str(other.get("priority", "")).upper(), 0)
    if other_p > base_p:
        merged["priority"] = other["priority"]

    # required, previously_failed는 OR 결합 (안전 우선)
    merged["required"] = bool(merged.get("required")) or bool(other.get("required"))
    merged["previously_failed"] = bool(merged.get("previously_failed")) or bool(
        other.get("previously_failed")
    )

    return merged
