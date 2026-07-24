"""OpenAILLMClient 테스트.

실제 openai 패키지 없이도 테스트할 수 있도록, openai.OpenAI().chat.completions.create()
와 동일한 인터페이스를 갖는 fake 객체를 사용한다.
"""

import unittest

from app.infrastructure.openai_llm_client import DEFAULT_SEED, OpenAILLMClient


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    """실제 호출 인자를 기록해서 테스트에서 검증할 수 있게 한다."""

    def __init__(self, content: str | None = '{"ok": true}') -> None:
        self._content = content
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeOpenAIClient:
    def __init__(self, content: str | None = '{"ok": true}') -> None:
        self.completions = _FakeCompletions(content)
        self.chat = _FakeChat(self.completions)


class _DummySchema:
    """response_schema 인자로 사용할 최소 더미. model_json_schema만 있으면 됨."""

    @staticmethod
    def model_json_schema():
        return {"type": "object", "properties": {}}


class OpenAILLMClientHappyPathTest(unittest.TestCase):
    def test_returns_message_content(self) -> None:
        fake = _FakeOpenAIClient(content='{"result": "ok"}')
        client = OpenAILLMClient(fake, model="gpt-4o")

        result = client.generate_structured(
            system_prompt="sys", user_prompt="usr", response_schema=_DummySchema
        )
        self.assertEqual(result, '{"result": "ok"}')

    def test_temperature_and_seed_are_fixed_for_determinism(self) -> None:
        fake = _FakeOpenAIClient()
        client = OpenAILLMClient(fake, model="gpt-4o", seed=42)

        client.generate_structured(system_prompt="sys", user_prompt="usr", response_schema=_DummySchema)

        kwargs = fake.completions.last_kwargs
        self.assertEqual(kwargs["temperature"], 0)
        self.assertEqual(kwargs["seed"], 42)

    def test_default_seed_used_when_not_specified(self) -> None:
        fake = _FakeOpenAIClient()
        client = OpenAILLMClient(fake, model="gpt-4o")
        client.generate_structured(system_prompt="sys", user_prompt="usr", response_schema=_DummySchema)
        self.assertEqual(fake.completions.last_kwargs["seed"], DEFAULT_SEED)

    def test_messages_include_system_and_user_prompts(self) -> None:
        fake = _FakeOpenAIClient()
        client = OpenAILLMClient(fake, model="gpt-4o")
        client.generate_structured(
            system_prompt="시스템 지시문", user_prompt="사용자 프롬프트", response_schema=_DummySchema
        )

        messages = fake.completions.last_kwargs["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "시스템 지시문"})
        self.assertEqual(messages[1], {"role": "user", "content": "사용자 프롬프트"})

    def test_response_format_uses_strict_json_schema(self) -> None:
        fake = _FakeOpenAIClient()
        client = OpenAILLMClient(fake, model="gpt-4o")
        client.generate_structured(system_prompt="sys", user_prompt="usr", response_schema=_DummySchema)

        fmt = fake.completions.last_kwargs["response_format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["json_schema"]["name"], "_DummySchema")
        self.assertTrue(fmt["json_schema"]["strict"])

    def test_model_name_is_forwarded(self) -> None:
        fake = _FakeOpenAIClient()
        client = OpenAILLMClient(fake, model="gpt-4o-mini")
        client.generate_structured(system_prompt="sys", user_prompt="usr", response_schema=_DummySchema)
        self.assertEqual(fake.completions.last_kwargs["model"], "gpt-4o-mini")


class OpenAILLMClientErrorHandlingTest(unittest.TestCase):
    def test_none_content_raises_value_error(self) -> None:
        """콘텐츠 필터 등으로 content가 None이면 명시적으로 오류를 낸다."""
        fake = _FakeOpenAIClient(content=None)
        client = OpenAILLMClient(fake, model="gpt-4o")

        with self.assertRaisesRegex(ValueError, "content가 없습니다"):
            client.generate_structured(system_prompt="sys", user_prompt="usr", response_schema=_DummySchema)


class OpenAILLMClientInstanceSeparationTest(unittest.TestCase):
    def test_separate_instances_can_use_different_models_on_shared_raw_client(self) -> None:
        """같은 raw client를 공유해도 인스턴스별로 다른 model을 쓸 수 있어야 함."""
        fake = _FakeOpenAIClient()
        action_llm = OpenAILLMClient(fake, model="gpt-4o")
        validator_llm = OpenAILLMClient(fake, model="gpt-4o-mini")

        action_llm.generate_structured(system_prompt="a", user_prompt="a", response_schema=_DummySchema)
        self.assertEqual(fake.completions.last_kwargs["model"], "gpt-4o")

        validator_llm.generate_structured(system_prompt="v", user_prompt="v", response_schema=_DummySchema)
        self.assertEqual(fake.completions.last_kwargs["model"], "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
