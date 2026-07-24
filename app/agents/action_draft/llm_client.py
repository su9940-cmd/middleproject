"""
LLM 클라이언트 프로토콜.

Action Draft는 이 Protocol에만 의존한다. 실제 구현(OpenAI, Anthropic, Bedrock 등)은
D의 스케줄레이션 계층에서 주입한다.

안전장치 4 (결정론성):
    - 구현체는 temperature=0, seed 고정으로 설정되어야 한다.
    - 이 계약은 프로토콜 문서화로만 표현하며 런타임에 강제되지 않는다.
    - D가 실제 클라이언트를 만들 때 이 두 파라미터를 반드시 고정해야 한다.
"""

from typing import Protocol


class LLMClient(Protocol):
    """구조화된 JSON을 반환하는 LLM 클라이언트.

    LangGraph 노드에서 동기 호출로 사용된다. 비동기가 필요하면 async 프로토콜을
    별도로 정의하고 draft_composer에서 분기한다.
    """

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: type,
    ) -> str:
        """system_prompt와 user_prompt로 LLM을 호출하고 JSON 문자열을 반환한다.

        Args:
            system_prompt: 안전장치·역할·제약을 설명하는 시스템 지시문
            user_prompt: RAG 문서·Memory 힌트·상황 요약이 들어간 사용자 지시문
            response_schema: 응답이 만족해야 할 Pydantic 모델 클래스
                             (구현체는 이를 통해 스키마 강제 - function calling 등 활용)

        Returns:
            응답 JSON 문자열. 파싱은 호출자(draft_composer)가 담당한다.

        Raises:
            LLM 호출 실패, 타임아웃, 응답 없음 등을 구현체가 예외로 표현하며,
            draft_composer가 잡아서 ActionDraftError로 변환한다.
        """
        ...
