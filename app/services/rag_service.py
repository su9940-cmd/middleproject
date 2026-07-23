"""RAG 검색 서비스.

설비별 SOP·법령·KOSHA 문서를 적재한 Vector DB에 대해
메타데이터 필터 기반 유사도 검색을 수행한다.

민감정보(경로, 임베딩 모델명 등)는 core.config를 통해 주입받는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.enums import MachineType


# ML 모델 컬럼이 아니라, 설비 ID → 매뉴얼 ID 매핑.
# 값이 없는 경우를 대비해 machine_type 기반 폴백도 둔다.
MACHINE_MANUAL_MAP: dict[str, str] = {
    "M-0101": "reactor_safety_manual",
    "M-0102": "compressor_safety_manual",
    "M-0103": "storage_tank_safety_manual",
    "M-0104": "pump_safety_manual",
}

MACHINE_TYPE_MANUAL_MAP: dict[MachineType, str] = {
    MachineType.REACTOR: "reactor_safety_manual",
    MachineType.COMPRESSOR: "compressor_safety_manual",
    MachineType.STORAGE_TANK: "storage_tank_safety_manual",
    MachineType.PUMP: "pump_safety_manual",
}


class VectorStore(Protocol):
    """Vector DB 어댑터 인터페이스.

    구체 구현(Chroma 등)은 이 프로토콜을 만족하면 교체 가능하다.
    """

    def query(
        self,
        query_text: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """query_text에 대해 top_k개의 청크를 검색한다.

        각 결과는 최소한 다음 키를 포함해야 한다:
        source_id, document_type, title, section, content,
        relevance_score, manual_version.
        """
        ...


@dataclass(frozen=True)
class RetrievalRequest:
    """RAG 검색 요청 파라미터."""

    machine_id: str
    machine_type: MachineType
    query_text: str
    manual_id: str | None = None
    top_k: int = 5


def resolve_manual_id(
    machine_id: str | None,
    machine_type: MachineType | str | None,
    manual_id: str | None = None,
) -> str:
    """설비 식별 정보로부터 매뉴얼 ID를 결정한다.

    두 경우를 모두 방어적으로 처리한다.
      - 앞단 노드가 state.manual_id를 채워 넘긴 경우: 그 값을 신뢰해 그대로 사용
      - machine_type만 넘어온 경우: 타입 매핑으로 폴백

    우선순위(팀 방침): 명시된 manual_id > machine_type 매핑 > machine_id 매핑.
    machine_type은 StrEnum이라 항상 정확하고 SOP와 1:1로 대응하므로
    machine_id 매핑보다 신뢰도가 높아 우선한다. machine_id 매핑은
    machine_type을 해석할 수 없을 때의 최종 폴백으로만 사용한다.

    어느 것으로도 결정할 수 없으면 ValueError를 발생시킨다.
    machine_type은 StrEnum이거나 문자열("REACTOR")로 올 수 있으므로
    두 형태를 모두 허용한다.
    """
    # 1) 명시된 manual_id 우선 (공백만 있는 값은 무시)
    if manual_id and manual_id.strip():
        return manual_id.strip()

    # 2) machine_type 매핑 (enum·문자열 모두 허용, 신뢰도 우선)
    if machine_type is not None:
        try:
            machine_type_enum = MachineType(machine_type)
        except ValueError:
            machine_type_enum = None
        if machine_type_enum in MACHINE_TYPE_MANUAL_MAP:
            return MACHINE_TYPE_MANUAL_MAP[machine_type_enum]

    # 3) machine_id 매핑 (최종 폴백)
    if machine_id and machine_id.strip() in MACHINE_MANUAL_MAP:
        return MACHINE_MANUAL_MAP[machine_id.strip()]

    raise ValueError(
        f"매뉴얼을 결정할 수 없습니다: machine_id={machine_id}, "
        f"machine_type={machine_type}"
    )



def build_metadata_filter(
    manual_id: str,
    document_types: tuple[str, ...] = ("sop", "law"),
) -> dict[str, Any]:
    """설비 매뉴얼에 검색을 한정하는 메타데이터 필터를 생성한다.

    chromadb 1.x는 메타데이터 값으로 리스트를 지원하지 않으므로,
    적재 시점에 조문을 적용 설비 수만큼 복제해 각 청크에 단일 manual_id를
    부여한다. 따라서 여기서는 단순 일치 매칭으로 필터링한다.
    """
    return {
        "$and": [
            {"manual_id": manual_id},
            {"document_type": {"$in": list(document_types)}},
        ]
    }



def normalize_retrieved_documents(
    raw_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Vector DB 원시 결과를 공통 retrieved_documents 형식으로 정규화한다.

    누락된 선택 필드(section, relevance_score, manual_version)는 None으로 채운다.
    필수 필드(source_id, document_type, title, content)가 없으면 건너뛴다.
    """
    normalized: list[dict[str, Any]] = []
    for item in raw_results:
        source_id = item.get("source_id")
        document_type = item.get("document_type")
        title = item.get("title")
        content = item.get("content")
        if not (source_id and document_type and title and content):
            # 필수 필드 결손 청크는 근거로 쓸 수 없으므로 제외한다.
            continue
        normalized.append(
            {
                "source_id": source_id,
                "document_type": document_type,
                "title": title,
                "section": item.get("section"),
                "content": content,
                "relevance_score": item.get("relevance_score"),
                "manual_version": item.get("manual_version"),
            }
        )
    return normalized


def retrieve_documents(
    vector_store: VectorStore,
    request: RetrievalRequest,
) -> list[dict[str, Any]]:
    """검색 요청을 수행하고 공통 형식의 문서 리스트를 반환한다.

    상위(rag_agent)에서 예외를 오류 계약으로 변환할 수 있도록
    여기서는 예외를 삼키지 않고 그대로 전파한다.
    """
    settings = get_settings()
    manual_id = resolve_manual_id(
        machine_id=request.machine_id,
        machine_type=request.machine_type,
        manual_id=request.manual_id,
    )
    metadata_filter = build_metadata_filter(manual_id)
    raw_results = vector_store.query(
        query_text=request.query_text,
        top_k=request.top_k or settings.rag_default_top_k,
        metadata_filter=metadata_filter,
    )
    return normalize_retrieved_documents(raw_results)
