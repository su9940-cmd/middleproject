"""Grounded draft composer tests."""

import json
import unittest

from app.agents.action_draft.draft_composer import compose_llm_draft
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
        first_item = _compose(FakeLLMClient(_response()))[0][0]
        items, _, _, _ = _compose(
            FakeLLMClient(_response()),
            memory={"completed_action_ids": [first_item["action_id"]]},
        )
        self.assertEqual(items, [])

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
