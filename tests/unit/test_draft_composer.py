"""draft_composer 테스트 - 4개 안전장치 검증.

Fake LLM 클라이언트로 LLM 응답을 제어하여 각 안전장치를 개별 검증한다.
"""

import json
import unittest

from app.agents.action_draft.draft_composer import compose_llm_draft
from app.core.enums import RiskLevel


class FakeLLMClient:
    """미리 정의된 응답을 반환하는 fake LLM."""

    def __init__(self, response) -> None:
        self._response = response
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    def generate_structured(self, *, system_prompt: str, user_prompt: str, response_schema: type) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _doc(source_id="SOP-R-014", document_type="SOP", title="냉각수", content="밸브 A-3"):
    return {
        "source_id": source_id,
        "document_type": document_type,
        "title": title,
        "content": content,
    }


def _llm_response(actions):
    return json.dumps({"summary": "테스트 요약", "actions": actions})


def _llm_action(source_id="SOP-R-014", action_id=None, **overrides):
    action = {
        "action_id": action_id or source_id,
        "title": "냉각수 확인",
        "description": "밸브 A-3 확인",
        "priority": "HIGH",
        "required": True,
        "source_ids": [source_id],
        "previously_failed": False,
    }
    action.update(overrides)
    return action


class ComposeLlmDraftHappyPathTest(unittest.TestCase):
    def test_valid_llm_response_produces_actions(self) -> None:
        llm = FakeLLMClient(_llm_response([_llm_action()]))
        actions, summary, used_fallback = compose_llm_draft(
            llm=llm,
            documents=[_doc()],
            memory_context={},
            risk_level=RiskLevel.WARNING,
            emergency_reasons=[],
        )
        self.assertEqual(len(actions), 1)
        self.assertFalse(used_fallback)
        self.assertEqual(summary, "테스트 요약")

    def test_llm_action_fields_forwarded(self) -> None:
        llm = FakeLLMClient(_llm_response([_llm_action()]))
        actions, _, _ = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        action = actions[0]
        self.assertGreaterEqual(
            set(action.keys()),
            {"action_id", "title", "description", "priority", "required", "source_ids", "previously_failed"},
        )


class ComposeLlmDraftGuard1Test(unittest.TestCase):
    """안전장치 1: RAG 원문 벗어난 창작 금지."""

    def test_action_with_hallucinated_source_id_dropped(self) -> None:
        """LLM이 실제 문서에 없는 source_id를 만들어내면 제외해야 함."""
        llm = FakeLLMClient(_llm_response([
            _llm_action(source_id="SOP-R-014"),
            _llm_action(source_id="SOP-FAKE-999", action_id="FAKE"),
        ]))
        actions, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["source_ids"], ["SOP-R-014"])
        self.assertFalse(used_fallback)

    def test_all_hallucinated_falls_back_to_documents(self) -> None:
        """LLM 조치가 전부 환각이면 fallback으로 규칙 기반 조립."""
        llm = FakeLLMClient(_llm_response([_llm_action(source_id="SOP-FAKE", action_id="FAKE")]))
        actions, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["source_ids"], ["SOP-R-014"])


class ComposeLlmDraftGuard2Test(unittest.TestCase):
    """안전장치 2: source_id 가드 (스키마 + 재검증)."""

    def test_action_with_empty_source_ids_rejected_by_schema(self) -> None:
        """LLM이 source_ids를 빈 배열로 반환하면 Pydantic 검증 실패 -> fallback."""
        llm = FakeLLMClient(_llm_response([_llm_action(source_ids=[])]))
        _, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)


class ComposeLlmDraftGuard3Test(unittest.TestCase):
    """안전장치 3: Pydantic 구조화 출력 강제."""

    def test_malformed_json_triggers_fallback(self) -> None:
        llm = FakeLLMClient("not a json {{{")
        _, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)

    def test_schema_violation_triggers_fallback(self) -> None:
        """LLM이 잘못된 priority 값을 반환하면 스키마 위반 -> fallback."""
        llm = FakeLLMClient(_llm_response([_llm_action(priority="URGENT")]))
        _, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)

    def test_llm_exception_triggers_fallback(self) -> None:
        """LLM 호출 자체가 실패해도 fallback으로 조치를 만들 수 있어야 함."""
        llm = FakeLLMClient(RuntimeError("LLM API down"))
        _, _, used_fallback = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)


class ComposeLlmDraftMemoryContextTest(unittest.TestCase):
    def test_completed_action_ids_excluded_from_llm_output(self) -> None:
        llm = FakeLLMClient(_llm_response([
            _llm_action(source_id="SOP-R-014", action_id="SOP-R-014"),
            _llm_action(source_id="SOP-R-015", action_id="SOP-R-015"),
        ]))
        docs = [_doc(source_id="SOP-R-014"), _doc(source_id="SOP-R-015", title="다른")]
        memory = {"completed_action_ids": ["SOP-R-014"]}

        actions, _, _ = compose_llm_draft(
            llm=llm, documents=docs, memory_context=memory, risk_level=RiskLevel.CAUTION, emergency_reasons=[],
        )
        self.assertEqual([a["action_id"] for a in actions], ["SOP-R-015"])

    def test_previously_failed_flag_forced_by_memory(self) -> None:
        """LLM이 previously_failed=False로 반환해도 memory에 있으면 True로 강제."""
        llm = FakeLLMClient(_llm_response([_llm_action(previously_failed=False)]))
        memory = {"failed_action_ids": ["SOP-R-014"]}

        actions, _, _ = compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context=memory, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(actions[0]["previously_failed"])


class ComposeLlmDraftFallbackTest(unittest.TestCase):
    def test_fallback_preserves_source_id_traceability(self) -> None:
        llm = FakeLLMClient("invalid json")
        docs = [_doc(source_id="SOP-1"), _doc(source_id="SOP-2", title="다른")]

        actions, _, used_fallback = compose_llm_draft(
            llm=llm, documents=docs, memory_context={}, risk_level=RiskLevel.WARNING, emergency_reasons=[],
        )
        self.assertTrue(used_fallback)
        ids = {a["action_id"] for a in actions}
        self.assertEqual(ids, {"SOP-1", "SOP-2"})

    def test_fallback_skips_documents_without_source_id(self) -> None:
        llm = FakeLLMClient(RuntimeError("down"))
        docs = [_doc(source_id=None), _doc(source_id="SOP-VALID")]

        actions, _, _ = compose_llm_draft(
            llm=llm, documents=docs, memory_context={}, risk_level=RiskLevel.CAUTION, emergency_reasons=[],
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_id"], "SOP-VALID")


class ComposeLlmDraftPromptTest(unittest.TestCase):
    def test_prompt_includes_completed_and_failed_action_hints(self) -> None:
        llm = FakeLLMClient(_llm_response([_llm_action()]))
        memory = {
            "completed_action_ids": ["OLD-1"],
            "failed_action_ids": ["OLD-2"],
            "latest_worker_note": "냉각수 부족 의심",
        }
        compose_llm_draft(
            llm=llm, documents=[_doc()], memory_context=memory,
            risk_level=RiskLevel.EMERGENCY, emergency_reasons=["Temp>=42"],
        )
        prompt = llm.last_user_prompt
        self.assertIn("OLD-1", prompt)
        self.assertIn("OLD-2", prompt)
        self.assertIn("냉각수 부족 의심", prompt)
        self.assertIn("Temp>=42", prompt)
        self.assertIn("EMERGENCY", prompt)

    def test_prompt_only_includes_documents_with_source_id(self) -> None:
        llm = FakeLLMClient(_llm_response([_llm_action()]))
        docs = [_doc(source_id=None, title="근거없음"), _doc(source_id="VALID")]
        compose_llm_draft(
            llm=llm, documents=docs, memory_context={},
            risk_level=RiskLevel.CAUTION, emergency_reasons=[],
        )
        self.assertNotIn("근거없음", llm.last_user_prompt)
        self.assertIn("VALID", llm.last_user_prompt)


if __name__ == "__main__":
    unittest.main()
