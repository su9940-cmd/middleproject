"""RAG 검색 동작 확인용 임시 스크립트.

인덱싱된 Chroma 컬렉션에 실제 질의를 날려
- 검색 결과가 나오는지
- manual_id 필터가 설비별로 잘 걸리는지
를 눈으로 확인한다. (정식 평가가 아닌 스모크 테스트)

실행: python scripts/test_search.py
"""

from __future__ import annotations

from app.core.enums import MachineType
from app.services.rag_service import RetrievalRequest, retrieve_documents
from app.services.vector_store_chroma import ChromaVectorStore


def print_results(title: str, docs: list[dict]) -> None:
    print("=" * 70)
    print(f"[질의] {title}")
    print("-" * 70)
    if not docs:
        print("  (검색 결과 없음)")
        return
    for i, d in enumerate(docs, 1):
        score = d.get("relevance_score")
        score_str = f"{score:.3f}" if score is not None else "N/A"
        print(f"  {i}. [{d.get('document_type')}] {d.get('title')}")
        print(f"     manual/section: {d.get('section')}  score={score_str}")
        preview = (d.get("content") or "").replace("\n", " ")[:60]
        print(f"     내용: {preview}...")
    print()


def main() -> None:
    store = ChromaVectorStore()

    # 케이스 1: 압축기 질의 → 압축기 SOP가 상위에 나와야 함
    req1 = RetrievalRequest(
        machine_id="M-0102",
        machine_type=MachineType.COMPRESSOR,
        query_text="압축기 진동이 높을 때 어떻게 조치하나요?",
        top_k=3,
    )
    print_results("압축기 진동 조치 (M-0102, COMPRESSOR)", retrieve_documents(store, req1))

    # 케이스 2: 펌프 질의 → 펌프 SOP만 나와야 함 (압축기 섞이면 안 됨)
    req2 = RetrievalRequest(
        machine_id="M-0104",
        machine_type=MachineType.PUMP,
        query_text="펌프 유량이 최소 유량 밑으로 떨어지면?",
        top_k=3,
    )
    print_results("펌프 최소유량 (M-0104, PUMP)", retrieve_documents(store, req2))

    # 케이스 3: 법령 관련 질의 → 해당 설비로 복제된 법령 청크가 나오는지
    req3 = RetrievalRequest(
        machine_id="M-0101",
        machine_type=MachineType.REACTOR,
        query_text="정비 작업 시 운전을 정지하고 잠금장치를 해야 하나요?",
        top_k=3,
    )
    print_results("정비 시 운전정지 (M-0101, REACTOR)", retrieve_documents(store, req3))


if __name__ == "__main__":
    main()
