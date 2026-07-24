"""
OpenAI 기반 LLMClient 구현 (제안 사항).

주의: 이 파일은 B가 제안하는 예시이며, 실제 배포 전 D(스케줄레이션)의
검토 및 최종 LLM 서비스 결정(OpenAI 유지 / 다른 서비스로 교체)이 필요합니다.

Action Draft와 Validator가 동일한 LLMClient Protocol을 사용하므로,
이 구현체 하나로 양쪽에 서로 다른 설정(모델 등)을 준 인스턴스를 각각 주입할 수 있습니다.

의존성: pip install openai
"""

from __future__ import annotations

from typing import Any

# 결정론성 확보 (안전장치 4). 합의 후 app/core/config.py로 이관 권장.
DEFAULT_SEED = 20260723


class OpenAILLMClient:
    """LLMClient 프로토콜을 만족하는 OpenAI 구현체.

    이 클래스는 openai 패키지를 직접 import하지 않고, 이미 생성된 클라이언트
    인스턴스를 주입받는다. 두 가지 이유가 있다:
        1. 테스트 시 fake 객체로 손쉽게 대체 가능 (openai 패키지 없이도 테스트)
        2. API 키 관리(환경변수, 시크릿 매니저 등)를 이 클래스가 직접 알지 않음
           -> D의 스케줄레이션 계층이 클라이언트 생성과 키 관리를 전담

    사용 예:
        from openai import OpenAI

        raw_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        action_llm = OpenAILLMClient(raw_client, model="gpt-4o")
        validator_llm = OpenAILLMClient(raw_client, model="gpt-4o-mini")

        action_draft_agent = ActionDraftAgent(llm_client=action_llm)
        validator_agent = ValidatorAgent(llm_client=validator_llm)
    """

    def __init__(self, client: Any, *, model: str, seed: int = DEFAULT_SEED) -> None:
        """
        Args:
            client: openai.OpenAI(...) 인스턴스 (또는 동일 인터페이스의 fake).
            model: 사용할 모델명 (예: "gpt-4o", "gpt-4o-mini").
            seed: 결정론성 확보용 고정 seed (안전장치 4). 모델·서비스가 seed를
                  완벽히 보장하지 않을 수 있으므로 결정론성은 "최선 노력"이며,
                  Action Draft/Validator의 규칙 기반 안전장치가 최종 방어선이다.
        """
        self._client = client
        self._model = model
        self._seed = seed

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: type,
    ) -> str:
        """OpenAI structured output(JSON Schema strict mode)으로 호출한다.

        Raises:
            ValueError: 응답의 content가 없는 경우 (예: 콘텐츠 필터에 의한 refusal).
                        호출자(draft_composer, safety_judge)가 이를 잡아 fallback 처리한다.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,  # 안전장치 4: 결정론성
            seed=self._seed,  # 안전장치 4: 결정론성
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                    "strict": True,
                },
            },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError(
                "OpenAI 응답에 content가 없습니다 (콘텐츠 필터·refusal 가능성)"
            )
        return content
