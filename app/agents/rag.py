"""RAG 에이전트 노드.

경고·긴급 등급 통보 시 병렬 팬아웃으로 실행되어, 현재 설비의 SOP·법령
근거 문서를 검색해 state.retrieved_documents에 채운다.

계약(공통 State 규약):
  - 정상: {"retrieved_documents": [...]} 만 반환
  - 실패: 오류 계약(error_code, error_message, failed_node)과
          빈 retrieved_documents를 함께 반환
노드는 자신이 변경하는 필드만 반환한다.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import RiskLevel
from app.core.exceptions import RAGRetrievalError
from app.graph.state import SafetyState
from app.services.rag_service import RetrievalRequest, retrieve_documents
from app.services.vector_store_factory import get_vector_store


def build_query_text(state: SafetyState) -> str:
    """State 정보로 검색 질의문을 구성한다.

    설비 유형·위험 등급·긴급 사유를 결합해 관련 조치·근거 문서가
    상위에 오도록 한다.
    """
    parts: list[str] = []

    machine_type = state.get("machine_type")
    if machine_type is not None:
        parts.append(str(machine_type))

    risk_level = state.get("risk_level")
    if risk_level is not None:
        parts.append(f"{risk_level} 등급 대응 조치")

    emergency_reasons = state.get("emergency_reasons") or []
    if emergency_reasons:
        parts.append("긴급 사유: " + ", ".join(emergency_reasons))

    if not parts:
        # 최소한의 질의문 보장 (빈 질의로 인한 검색 실패 방지)
        parts.append("설비 안전 조치")

    return " / ".join(parts)


def rag_agent(state: SafetyState) -> dict[str, Any]:
    """현재 통보 건에 대한 근거 문서를 검색한다.

    이 노드가 변경하는 필드만 반환한다. 실패 시 오류 계약과 함께
    빈 retrieved_documents를 반환해 병렬 병합 시 키 결손을 방지한다.

    Args:
        state: 공통 SafetyState. machine_id/machine_type은 항상 존재하며,
            manual_id는 앞단 노드가 채웠을 수도, 비어 있을 수도 있다.

    Returns:
        정상: {"retrieved_documents": list[dict]}
        실패: 오류 계약 필드 + {"retrieved_documents": []}
    """
    # machine_id·machine_type은 총 4개 데모 설비 기준으로 항상 존재한다고 보되,
    # 방어적으로 .get()으로 접근한다(SafetyState는 total=False).
    machine_id = state.get("machine_id")
    machine_type = state.get("machine_type")

    if machine_id is None or machine_type is None:
        return {
            "error_code": RAGRetrievalError.error_code,
            "error_message": "machine_id 또는 machine_type이 없어 검색할 수 없습니다.",
            "failed_node": "rag_agent",
            "retrieved_documents": [],
        }

    try:
        request = RetrievalRequest(
            machine_id=machine_id,
            machine_type=machine_type,
            query_text=build_query_text(state),
            # 앞단이 채웠으면 신뢰해 그대로 전달, 없으면 None → 서비스에서 폴백
            manual_id=state.get("manual_id"),
        )
        documents = retrieve_documents(get_vector_store(), request)
        return {"retrieved_documents": documents}
    except ValueError as exc:
        # resolve_manual_id 실패 등 입력성 오류
        return {
            "error_code": RAGRetrievalError.error_code,
            "error_message": str(exc),
            "failed_node": "rag_agent",
            "retrieved_documents": [],
        }
    except Exception as exc:  # Vector DB 등 백엔드 오류
        return {
            "error_code": RAGRetrievalError.error_code,
            "error_message": f"문서 검색 중 오류가 발생했습니다: {exc}",
            "failed_node": "rag_agent",
            "retrieved_documents": [],
        }
