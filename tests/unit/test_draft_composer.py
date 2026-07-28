"""Grounded draft composer tests."""

import json
import unittest

from app.agents.action_draft.draft_composer import _extract_risk_section, compose_llm_draft
from app.core.enums import RiskLevel


class FakeLLMClient:
    def __init__(self, response) -> None:
        self.response = response
        self.last_user_prompt = None

    def generate_structured(self, *, system_prompt, user_prompt, response_schema):
        self.last_user_prompt = user_prompt
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _doc(
    source_id="pump_safety_manual",
    document_type="sop",
    section="4.3",
    title="흡입 배관 확인",
    content="흡입 밸브 개도와 배관 막힘 여부를 확인한다.",
):
    return {
        "source_id": source_id,
        "document_type": document_type,
        "section": section,
        "title": title,
        "content": content,
        "manual_version": "1.5",
    }


def _action(source_key="pump_safety_manual::4.3", **overrides):
    value = {
        "title": "흡입 배관 확인",
        "instruction": "흡입 밸브 개도와 배관 막힘 여부를 확인한다.",
        "priority": "HIGH",
        "required": True,
        "source_keys": [source_key],
        "previously_failed": False,
    }
    value.update(overrides)
    return value


def _response(actions=None):
    return json.dumps(
        {"summary": "펌프 저압 대응", "actions": actions or [_action()]},
        ensure_ascii=False,
    )


def _compose(llm, documents=None, memory=None, **kwargs):
    return compose_llm_draft(
        llm=llm,
        documents=documents if documents is not None else [_doc()],
        memory_context=memory or {},
        risk_level=kwargs.pop("risk_level", RiskLevel.WARNING),
        emergency_reasons=kwargs.pop("emergency_reasons", []),
        **kwargs,
    )


class ComposeHappyPathTest(unittest.TestCase):
    def test_valid_response_gets_server_ids_and_exact_citation(self) -> None:
        items, summary, fallback, references = _compose(FakeLLMClient(_response()))

        self.assertEqual(summary, "펌프 저압 대응")
        self.assertFalse(fallback)
        self.assertEqual(references, [])
        self.assertTrue(items[0]["action_id"].startswith("ACTION-"))
        self.assertTrue(items[0]["checklist_item_id"].startswith("ITEM-"))
        self.assertEqual(
            items[0]["citations"][0]["source_excerpt"],
            "흡입 밸브 개도와 배관 막힘 여부를 확인한다.",
        )

    def test_same_sources_and_title_produce_stable_ids(self) -> None:
        first = _compose(FakeLLMClient(_response()))[0][0]
        second = _compose(FakeLLMClient(_response()))[0][0]
        self.assertEqual(first["action_id"], second["action_id"])
        self.assertEqual(first["checklist_item_id"], second["checklist_item_id"])


class ComposeGroundingGuardTest(unittest.TestCase):
    def test_unknown_source_key_is_replaced_by_sop_fallback(self) -> None:
        response = _response([_action(source_key="FAKE::1")])
        items, _, fallback, _ = _compose(FakeLLMClient(response))
        self.assertTrue(fallback)
        self.assertEqual(items[0]["citations"][0]["source_id"], "pump_safety_manual")

    def test_schema_failure_or_llm_failure_uses_sop_fallback(self) -> None:
        for response in ("not-json", RuntimeError("down")):
            with self.subTest(response=type(response).__name__):
                items, _, fallback, _ = _compose(FakeLLMClient(response))
                self.assertTrue(fallback)
                self.assertTrue(items[0]["required"])

    def test_completed_action_is_not_repeated(self) -> None:
        """A second, still-open action keeps the response non-empty, so this
        exercises `_apply_safety_guards`'s own completed-filter directly
        instead of also tripping the separate fallback-on-empty behavior
        (see `test_completed_fallback_step_is_not_repeated` for that path)."""

        second_doc = _doc(section="4.4", title="배출 밸브 확인", content="배출 밸브 개도를 확인한다.")
        second_action = _action(
            source_key="pump_safety_manual::4.4",
            title="배출 밸브 확인",
            instruction="배출 밸브 개도를 확인한다.",
        )
        response = _response([_action(), second_action])
        documents = [_doc(), second_doc]

        first_items = _compose(FakeLLMClient(response), documents=documents)[0]
        self.assertEqual(len(first_items), 2)
        completed_id = first_items[0]["action_id"]

        items, _, fallback, _ = _compose(
            FakeLLMClient(response),
            documents=documents,
            memory={"completed_action_ids": [completed_id]},
        )
        self.assertFalse(fallback)
        self.assertEqual(len(items), 1)
        self.assertNotEqual(items[0]["action_id"], completed_id)

    def test_completed_fallback_step_is_not_repeated(self) -> None:
        """Partial completion on the fallback path: one of several steps was
        already completed on a past alert, another wasn't - only the
        completed one is filtered out (fallback and LLM-path action ids are
        computed from different inputs - title vs. step text - so they're
        deliberately not interchangeable identity spaces)."""

        documents = [
            _doc(
                content=(
                    "## 4. 경고 등급 통보 시 조치\n"
                    "1. 흡입 밸브 개도를 확인한다.\n"
                    "2. 배관 막힘 여부를 점검한다.\n"
                ),
            )
        ]
        first_items = _compose(FakeLLMClient(RuntimeError("down")), documents=documents)[0]
        self.assertEqual(len(first_items), 2)
        completed_id = first_items[0]["action_id"]

        items, _, _, _ = _compose(
            FakeLLMClient(RuntimeError("down")),
            documents=documents,
            memory={"completed_action_ids": [completed_id]},
        )
        self.assertEqual(len(items), 1)
        self.assertNotEqual(items[0]["action_id"], completed_id)

    def test_fallback_recurrence_reissues_steps_instead_of_emptying_out(self) -> None:
        """If EVERY step for this risk level was already completed on a past
        alert (the hazard recurred after being fully handled once), the
        fallback has no other content to compose from - it must re-issue the
        same steps rather than filter down to an empty checklist, which used
        to surface to the worker as an opaque 500 ("no grounded SOP checklist
        items could be composed") the moment an emergency recurred on a
        machine whose prior checklist had been fully completed."""

        first_item = _compose(FakeLLMClient(RuntimeError("down")))[0][0]
        items, _, _, _ = _compose(
            FakeLLMClient(RuntimeError("down")),
            memory={"completed_action_ids": [first_item["action_id"]]},
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["action_id"], first_item["action_id"])

    def test_failed_action_is_marked_by_server(self) -> None:
        first_item = _compose(FakeLLMClient(_response()))[0][0]
        items, _, _, _ = _compose(
            FakeLLMClient(_response()),
            memory={"failed_action_ids": [first_item["action_id"]]},
        )
        self.assertTrue(items[0]["previously_failed"])


class ComposeDocumentTypeTest(unittest.TestCase):
    def test_fallback_uses_lowercase_sop_as_required_action(self) -> None:
        items, _, fallback, _ = _compose(FakeLLMClient(RuntimeError("down")))
        self.assertTrue(fallback)
        self.assertTrue(items[0]["required"])

    def test_law_is_reference_not_fallback_action(self) -> None:
        documents = [
            _doc(),
            _doc(
                source_id="law_art92",
                document_type="law",
                section="제92조",
                title="운전정지",
                content="정비 작업 시 필요한 안전조치를 검토한다.",
            ),
        ]
        items, _, fallback, references = _compose(
            FakeLLMClient(RuntimeError("down")), documents=documents
        )
        self.assertTrue(fallback)
        self.assertEqual(len(items), 1)
        self.assertEqual(references[0]["source_id"], "law_art92")

    def test_law_only_llm_action_is_rejected(self) -> None:
        law = _doc(
            source_id="law_art92",
            document_type="law",
            section="제92조",
            title="운전정지",
            content="정비 작업 시 필요한 안전조치를 검토한다.",
        )
        response = _response([_action(source_key="law_art92::제92조")])
        items, _, fallback, references = _compose(
            FakeLLMClient(response), documents=[law]
        )
        self.assertTrue(fallback)
        self.assertEqual(items, [])
        self.assertEqual(references[0]["source_id"], "law_art92")


_MULTI_SECTION_SOP = """---
doc_id: pump_safety_manual
---

# 펌프 위험 통보 대응 표준작업절차서

## 1. 적용 범위

절차서 개요.

## 3. 펌프 주의 등급 통보 시 조치

1. 지시값을 재확인한다.

## 4. 펌프 경고 등급 통보 시 조치

1. 접근을 제한한다.

## 5. 펌프 긴급 등급 통보 시 조치

1. 비상 정지한다.
2. 인원을 대피시킨다.

## 6. 펌프 원인 점검 절차

정비 담당자 전용 절차 - 초기 대응 대상이 아니다.
"""


class ExtractRiskSectionTest(unittest.TestCase):
    """A worker should see only the section for the *current* risk level,
    not the whole SOP (symptoms/root-cause/restart sections aren't the first
    responder's job)."""

    def test_emergency_returns_only_the_emergency_section(self) -> None:
        section = _extract_risk_section(_MULTI_SECTION_SOP, RiskLevel.EMERGENCY)
        self.assertIn("긴급 등급 통보 시 조치", section)
        self.assertIn("비상 정지한다", section)
        self.assertNotIn("경고 등급", section)
        self.assertNotIn("원인 점검", section)

    def test_warning_and_caution_pick_their_own_section(self) -> None:
        warning = _extract_risk_section(_MULTI_SECTION_SOP, RiskLevel.WARNING)
        self.assertIn("경고 등급 통보 시 조치", warning)
        self.assertIn("접근을 제한한다", warning)

        caution = _extract_risk_section(_MULTI_SECTION_SOP, "CAUTION")
        self.assertIn("주의 등급 통보 시 조치", caution)
        self.assertIn("지시값을 재확인한다", caution)

    def test_unmatched_risk_level_returns_full_content_unchanged(self) -> None:
        self.assertEqual(_extract_risk_section(_MULTI_SECTION_SOP, "NORMAL"), _MULTI_SECTION_SOP)

    def test_content_without_matching_headings_falls_back_to_full_text(self) -> None:
        plain_text = "설비 점검 지침입니다. 절 구분이 없습니다."
        self.assertEqual(_extract_risk_section(plain_text, RiskLevel.EMERGENCY), plain_text)

    def test_fallback_splits_the_section_into_one_item_per_step(self) -> None:
        """Each numbered step in the risk-level section becomes its own
        checklist item (title + instruction = that step alone), instead of
        one item holding the whole section - see risk_logic_flow.mp4's
        reference checklist: a handful of focused items, not one wall of
        text."""

        documents = [_doc(content=_MULTI_SECTION_SOP)]
        items, _, fallback, _ = _compose(
            FakeLLMClient(RuntimeError("down")),
            documents=documents,
            risk_level=RiskLevel.EMERGENCY,
        )
        self.assertTrue(fallback)
        instructions = [item["instruction"] for item in items]
        self.assertEqual(instructions, ["비상 정지한다.", "인원을 대피시킨다."])
        self.assertTrue(all("원인 점검" not in text for text in instructions))
        self.assertTrue(all(len(text) < len(_MULTI_SECTION_SOP) for text in instructions))

    def test_fallback_without_a_numbered_list_stays_one_item(self) -> None:
        """A document that doesn't use the numbered-step convention still
        produces exactly one item (the whole matched section), same as
        before splitting existed - nothing is silently dropped."""

        items, _, fallback, _ = _compose(FakeLLMClient(RuntimeError("down")))
        self.assertTrue(fallback)
        self.assertEqual(len(items), 1)


class ComposeRevisionPromptTest(unittest.TestCase):
    def test_prompt_contains_current_problem_and_validator_feedback(self) -> None:
        llm = FakeLLMClient(_response())
        _compose(
            llm,
            machine_id="M-0104",
            machine_type="PUMP",
            sensor_reading={"Pressure": 8.0, "Vibration": 4.8},
            ml_risk_score=0.72,
            risk_evidence=[{"sensor": "Vibration", "reason": "고진동"}],
            validation_feedback=[{"code": "UNSUPPORTED", "message": "근거 불충분"}],
            previous_draft={"checklist_id": "CL-OLD"},
            validation_attempts=1,
        )
        prompt = llm.last_user_prompt
        for expected in ("M-0104", "PUMP", "Vibration", "0.72", "근거 불충분", "CL-OLD"):
            self.assertIn(expected, prompt)


if __name__ == "__main__":
    unittest.main()
