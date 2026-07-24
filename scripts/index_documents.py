"""문서 인덱싱 스크립트.

data/sop, data/laws 아래의 마크다운 문서를 읽어
front-matter(메타데이터) 파싱 → 청킹 → 메타데이터 부착 → Chroma 적재까지 수행한다.

- SOP: `##` 절 단위로 청킹, manual_id(단일)로 필터.
- 법령: 조문 단위 청킹, manual_id(리스트)를 설비별로 복제 인덱싱.
- 평가 질문셋(rag_평가_질문셋.md)은 인덱싱 대상에서 제외한다.

config 키가 미확정이므로 경로·모델명은 임시 상수로 둔다. (TODO(config) 참고)
실행: python scripts/index_documents.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

# from app.core.config import get_settings  # TODO(config): config 확정 후 주입

# --- 임시 상수 (TODO(config): D팀 config 키 확정 후 settings로 대체) ---
_CHROMA_PATH = "./chroma_db"              # settings.chroma_path
_COLLECTION_NAME = "safety_documents"     # settings.chroma_collection_name
_EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"  # settings.embedding_model
# --------------------------------------------------------------------

# 프로젝트 루트 기준 데이터 경로
_ROOT = Path(__file__).resolve().parent.parent
_SOP_DIR = _ROOT / "data" / "sop"
_LAWS_DIR = _ROOT / "data" / "laws"

# 인덱싱에서 제외할 파일 (평가용 질문셋은 검색 대상이 아님)
_EXCLUDE_FILES = {"rag_평가_질문셋.md"}


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """마크다운 상단의 YAML front-matter와 본문을 분리한다.

    front-matter가 없으면 빈 dict와 원문 전체를 반환한다.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    front_matter = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return front_matter, body


def split_sop_sections(body: str) -> list[tuple[str, str]]:
    """SOP 본문을 `##` 절 단위로 분할한다.

    반환: [(섹션 제목, 섹션 내용), ...]
    최상단 `#` 문서 제목 앞부분은 무시하고 `##`부터 자른다.
    """
    sections: list[tuple[str, str]] = []
    # `## ` 로 시작하는 헤딩 기준 분할
    chunks = re.split(r"\n(?=##\s)", body)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("##"):
            continue  # 문서 제목(#)이나 서두는 건너뜀
        first_line, _, rest = chunk.partition("\n")
        section_title = first_line.lstrip("#").strip()
        sections.append((section_title, chunk))
    return sections


def build_sop_records(path: Path) -> list[dict[str, Any]]:
    """SOP 파일 하나를 청크 레코드 리스트로 변환한다."""
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    manual_id = meta.get("doc_id")  # SOP는 doc_id가 곧 manual_id
    records: list[dict[str, Any]] = []

    for idx, (section_title, content) in enumerate(split_sop_sections(body)):
        records.append(
            {
                "id": f"{manual_id}__sec{idx}",
                "content": content,
                "metadata": {
                    "source_id": meta.get("doc_id"),
                    "document_type": meta.get("doc_type", "sop"),
                    "title": section_title,
                    "section": section_title,
                    "manual_id": manual_id,       # 단일값 필터
                    "machine_type": meta.get("machine_type"),
                    "machine_id": meta.get("machine_id"),
                    "manual_version": str(meta.get("version", "")),
                },
            }
        )
    return records


def build_law_records(path: Path) -> list[dict[str, Any]]:
    """법령 파일 하나를 청크 레코드 리스트로 변환한다.

    manual_id 리스트를 펼쳐 각 설비별로 동일 조문 청크를 복제 인덱싱한다.
    (Chroma 1.x 단일값 필터 제약 우회)
    """
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    source_id = meta.get("source_id") or meta.get("doc_id")
    manual_ids = meta.get("manual_id") or []
    if isinstance(manual_ids, str):
        manual_ids = [manual_ids]

    records: list[dict[str, Any]] = []
    # 데모 규모: 조문 1개 = 1청크 (본문 전체)
    for manual_id in manual_ids:
        records.append(
            {
                "id": f"{meta.get('doc_id')}__{manual_id}",
                "content": body,
                "metadata": {
                    "source_id": source_id,
                    "document_type": meta.get("doc_type", "law"),
                    "title": f"{meta.get('law_name', '')} {meta.get('article', '')} ({meta.get('title', '')})".strip(),
                    "section": meta.get("article"),
                    "manual_id": manual_id,       # 설비별 복제
                    "law_name": meta.get("law_name"),
                    "article": meta.get("article"),
                    "manual_version": str(meta.get("law_version", "")),
                },
            }
        )
    return records


def collect_records() -> list[dict[str, Any]]:
    """SOP·법령 폴더를 순회하며 모든 청크 레코드를 수집한다."""
    records: list[dict[str, Any]] = []

    for path in sorted(_SOP_DIR.glob("*.md")):
        if path.name in _EXCLUDE_FILES:
            print(f"[skip] {path.name} (평가 질문셋 제외)")
            continue
        records.extend(build_sop_records(path))

    for path in sorted(_LAWS_DIR.glob("*.md")):
        if path.name in _EXCLUDE_FILES:
            continue
        records.extend(build_law_records(path))

    return records


def main() -> None:
    # TODO(config): 아래 상수들을 get_settings()로 대체
    embeddings = HuggingFaceEmbeddings(model_name=_EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=_CHROMA_PATH)

    # 기존 컬렉션이 있으면 삭제 후 재생성 (재인덱싱 시 중복 방지)
    try:
        client.delete_collection(_COLLECTION_NAME)
        print(f"[reset] 기존 컬렉션 '{_COLLECTION_NAME}' 삭제")
    except Exception:
        pass

    collection = client.create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # 어댑터의 1-distance 계산과 일치
    )

    records = collect_records()
    if not records:
        print("인덱싱할 문서가 없습니다.")
        return

    ids = [r["id"] for r in records]
    contents = [r["content"] for r in records]
    metadatas = [r["metadata"] for r in records]
    embeddings_vecs = embeddings.embed_documents(contents)

    collection.add(
        ids=ids,
        documents=contents,
        embeddings=embeddings_vecs,
        metadatas=metadatas,
    )

    print(f"[done] 총 {len(records)}개 청크 인덱싱 완료")
    # 문서 유형별 개수 요약
    sop_cnt = sum(1 for m in metadatas if m["document_type"] == "sop")
    law_cnt = sum(1 for m in metadatas if m["document_type"] == "law")
    print(f"  - SOP 청크: {sop_cnt}")
    print(f"  - 법령 청크(설비별 복제 포함): {law_cnt}")


if __name__ == "__main__":
    main()
