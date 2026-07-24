"""RAG 검색 품질 평가 스크립트.

data/sop/rag_평가_질문셋.md 의 질문을 파싱해 검색 파이프라인에 넣고,
Recall@3 와 MRR 을 계산한다.

- SOP 질문(설비별 표): 정답 '절 번호'로 매칭.
- 법령 질문(산안법 표): 정답 조문 번호(art 번호)로 매칭.
  각 법령이 연결된 대표 설비로 질의한다.
- 교차 검색 표(X): 서술형 기대동작이라 자동 채점에서 제외.

config 미확정 구간은 test_search 와 동일하게 임시값 사용.
실행: python -m scripts.evaluate_rag
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.core.enums import MachineType
from app.services.rag_service import RetrievalRequest, retrieve_documents
from app.services.vector_store_chroma import ChromaVectorStore

_ROOT = Path(__file__).resolve().parent.parent
_QUESTION_FILE = _ROOT / "data" / "sop" / "rag_평가_질문셋.md"
_LAWS_DIR = _ROOT / "data" / "laws"

# manual_id → (machine_id, machine_type) 매핑. 질의 시 RetrievalRequest 구성에 사용.
_MANUAL_TO_MACHINE: dict[str, tuple[str, MachineType]] = {
    "reactor_safety_manual": ("M-0101", MachineType.REACTOR),
    "compressor_safety_manual": ("M-0102", MachineType.COMPRESSOR),
    "storage_tank_safety_manual": ("M-0103", MachineType.STORAGE_TANK),
    "pump_safety_manual": ("M-0104", MachineType.PUMP),
}

_TOP_K = 3


def _extract_section_numbers(answer: str) -> list[str]:
    """정답 섹션 문자열에서 절 번호만 추출한다.

    예: '6. 원인 점검 / 9. 안전 규정' → ['6', '9']
    """
    return re.findall(r"(\d+)\s*\.", answer)


def _section_number_of(section: str | None) -> str | None:
    """검색된 청크 section 제목에서 맨 앞 절 번호를 추출한다.

    예: '3. 반응기 주의 등급 통보 시 조치' → '3'
    """
    if not section:
        return None
    m = re.match(r"\s*(\d+)\s*\.", section)
    return m.group(1) if m else None


def _art_number(text: str | None) -> str | None:
    """식별자에서 조문 번호를 추출한다.

    예: 'law_ind_safety_rule_art92' → '92'
        'law_art241_2' → '241_2'
        'law_art619'   → '619'
    """
    if not text:
        return None
    m = re.search(r"art(\d+(?:_\d+)?)", text)
    return m.group(1) if m else None


def _build_law_manual_map() -> dict[str, str]:
    """법령 파일들을 읽어 '조문번호 → 대표 manual_id' 매핑을 만든다.

    각 법령의 manual_id 리스트 중 첫 번째를 대표 설비로 사용한다.
    예: '93' → 'compressor_safety_manual'
    """
    art_to_manual: dict[str, str] = {}
    for path in _LAWS_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        meta = yaml.safe_load(parts[1]) or {}
        art_num = _art_number(meta.get("source_id") or meta.get("doc_id"))
        manual_ids = meta.get("manual_id") or []
        if isinstance(manual_ids, str):
            manual_ids = [manual_ids]
        if art_num and manual_ids:
            art_to_manual[art_num] = manual_ids[0]
    return art_to_manual


def parse_questions(text: str) -> tuple[list[dict], list[dict]]:
    """질문셋 마크다운을 파싱한다.

    반환: (sop_questions, law_questions)
    - sop_questions: {qid, manual_id, query, answer_sections(list[str])}
    - law_questions: {qid, query, expected_doc_id}
    """
    sop_questions: list[dict] = []
    law_questions: list[dict] = []

    current_manual: str | None = None
    mode: str | None = None  # "sop" | "law" | "cross"

    for line in text.splitlines():
        line = line.strip()

        # 섹션 헤딩 판별
        if line.startswith("## "):
            m = re.search(r"\(([a-z_]+_safety_manual)\)", line)
            if m:
                current_manual = m.group(1)
                mode = "sop"
            elif "산안법" in line or "law" in line.lower():
                mode = "law"
            elif "교차" in line:
                mode = "cross"
            else:
                mode = None
            continue

        # 표 데이터 행만 처리 ( | 로 시작, 구분선/헤더 제외 )
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        qid = cells[0]
        # 헤더행(#)이나 구분선(---) 건너뜀
        if qid in ("#", "") or set(qid) <= {"-"}:
            continue

        if mode == "sop" and current_manual:
            sop_questions.append(
                {
                    "qid": qid,
                    "manual_id": current_manual,
                    "query": cells[1],
                    "answer_sections": _extract_section_numbers(cells[2]),
                }
            )
        elif mode == "law":
            # expected_doc_id 는 마지막 셀에서 law_ 식별자 추출
            m = re.search(r"(law_[a-z0-9_]+)", cells[-1])
            law_questions.append(
                {
                    "qid": qid,
                    "query": cells[1],
                    "expected_doc_id": m.group(1) if m else None,
                }
            )
        # mode == "cross" 는 자동 채점 제외

    return sop_questions, law_questions


def evaluate() -> None:
    text = _QUESTION_FILE.read_text(encoding="utf-8")
    sop_qs, law_qs = parse_questions(text)
    store = ChromaVectorStore()

    recalls: list[float] = []
    rrs: list[float] = []  # reciprocal ranks

    print("=" * 70)
    print("[SOP 질문 평가]")
    print("-" * 70)
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

        recall = 1.0 if hit_rank else 0.0
        rr = 1.0 / hit_rank if hit_rank else 0.0
        recalls.append(recall)
        rrs.append(rr)

        status = f"rank={hit_rank}" if hit_rank else "miss"
        print(f"  {q['qid']:4} [{status:8}] 정답절={q['answer_sections']} "
              f"검색절={result_nums}")

    print()
    print("=" * 70)
    print("[법령 질문 평가]")
    print("-" * 70)
    law_manual_map = _build_law_manual_map()
    for q in law_qs:
        expected_num = _art_number(q["expected_doc_id"])
        # 리액터 고정 대신, 해당 법령이 연결된 대표 설비로 질의
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
            sid_num = _art_number(sid)
            if sid_num and sid_num == expected_num:
                hit_rank = rank
                break

        recall = 1.0 if hit_rank else 0.0
        rr = 1.0 / hit_rank if hit_rank else 0.0
        recalls.append(recall)
        rrs.append(rr)

        status = f"rank={hit_rank}" if hit_rank else "miss"
        print(f"  {q['qid']:4} [{status:8}] 정답={q['expected_doc_id']} "
              f"검색={result_ids} (질의설비={target_manual})")

    # 종합 지표
    n = len(recalls)
    print()
    print("=" * 70)
    print("[종합 결과]")
    print(f"  평가 문항 수: {n}")
    print(f"  Recall@{_TOP_K}: {sum(recalls) / n:.3f}")
    print(f"  MRR:       {sum(rrs) / n:.3f}")
    print("=" * 70)


if __name__ == "__main__":
    evaluate()
