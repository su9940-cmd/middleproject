"""청킹 전략 비교 스크립트.

세 가지 청킹 전략(section, fixed_512_50, fixed_1024_100)으로 인덱싱된
각 컬렉션에 대해 Recall@3 / MRR 을 계산하고 비교표를 출력한다.

전제: 먼저 `python -m scripts.index_documents --strategy all` 로
      세 컬렉션이 적재돼 있어야 한다.

실행: python -m scripts.compare_chunking
"""

from __future__ import annotations

from app.services.rag_service import RetrievalRequest, retrieve_documents
from app.services.vector_store_chroma import ChromaVectorStore

# evaluate_rag 의 파싱·채점 헬퍼를 재사용한다.
from scripts.evaluate_rag import (
    _MANUAL_TO_MACHINE,
    _TOP_K,
    _art_number,
    _build_law_manual_map,
    _section_number_of,
    parse_questions,
    _QUESTION_FILE,
)

_STRATEGIES = ("section", "fixed_512_50", "fixed_1024_100")
_COLLECTION_PREFIX = "safety_documents"


def evaluate_collection(collection_name: str) -> tuple[float, float, int]:
    """지정한 컬렉션으로 전체 질문을 평가해 (Recall@3, MRR, 문항수)를 반환한다."""
    text = _QUESTION_FILE.read_text(encoding="utf-8")
    sop_qs, law_qs = parse_questions(text)
    store = ChromaVectorStore(collection_name=collection_name)

    recalls: list[float] = []
    rrs: list[float] = []

    # SOP 질문
    for q in sop_qs:
        machine_id, machine_type = _MANUAL_TO_MACHINE[q["manual_id"]]
        req = RetrievalRequest(
            machine_id=machine_id,
            machine_type=machine_type,
            query_text=q["query"],
            top_k=_TOP_K,
        )
        docs = retrieve_documents(store, req)
        result_nums = [_section_number_of(d.get("section")) for d in docs]
        hit_rank = None
        for rank, num in enumerate(result_nums, 1):
            if num in q["answer_sections"]:
                hit_rank = rank
                break
        recalls.append(1.0 if hit_rank else 0.0)
        rrs.append(1.0 / hit_rank if hit_rank else 0.0)

    # 법령 질문
    law_manual_map = _build_law_manual_map()
    for q in law_qs:
        expected_num = _art_number(q["expected_doc_id"])
        target_manual = law_manual_map.get(expected_num, "reactor_safety_manual")
        machine_id, machine_type = _MANUAL_TO_MACHINE[target_manual]
        req = RetrievalRequest(
            machine_id=machine_id,
            machine_type=machine_type,
            query_text=q["query"],
            top_k=_TOP_K,
        )
        docs = retrieve_documents(store, req)
        result_ids = [d.get("source_id") for d in docs]
        hit_rank = None
        for rank, sid in enumerate(result_ids, 1):
            if _art_number(sid) and _art_number(sid) == expected_num:
                hit_rank = rank
                break
        recalls.append(1.0 if hit_rank else 0.0)
        rrs.append(1.0 / hit_rank if hit_rank else 0.0)

    n = len(recalls)
    return sum(recalls) / n, sum(rrs) / n, n


def main() -> None:
    print("=" * 60)
    print("청킹 전략 비교 (top_k=%d)" % _TOP_K)
    print("=" * 60)
    print(f"{'전략':<18}{'Recall@3':>12}{'MRR':>10}{'문항수':>8}")
    print("-" * 60)

    results = []
    for strategy in _STRATEGIES:
        collection_name = f"{_COLLECTION_PREFIX}__{strategy}"
        try:
            recall, mrr, n = evaluate_collection(collection_name)
        except Exception as e:
            print(f"{strategy:<18}  (평가 실패: {e})")
            continue
        results.append((strategy, recall, mrr))
        print(f"{strategy:<18}{recall:>12.3f}{mrr:>10.3f}{n:>8}")

    print("-" * 60)
    if results:
        best = max(results, key=lambda r: (r[1], r[2]))
        print(f"최고 성능: {best[0]} (Recall@3={best[1]:.3f}, MRR={best[2]:.3f})")
    print("=" * 60)


if __name__ == "__main__":
    main()
