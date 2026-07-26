"""문서 인덱싱 스크립트 (청킹 전략 비교 지원).

data/sop, data/laws 아래의 마크다운 문서를 읽어
front-matter 파싱 → 청킹 → 메타데이터 부착 → Chroma 적재까지 수행한다.

청킹 전략:
- section        : SOP는 `##` 절 단위, 법령은 조문 단위 (기본/의미 기반)
- fixed_512_50   : 고정 512자, 오버랩 50자
- fixed_1024_100 : 고정 1024자, 오버랩 100자

전략별로 별도 컬렉션(safety_documents__<전략>)에 적재해 비교 평가에 활용한다.
평가 질문셋(rag_평가_질문셋.md)은 인덱싱 대상에서 제외한다.

config 미확정이므로 경로·모델명은 임시 상수. (TODO(config) 참고)
실행:
    python -m scripts.index_documents                 # 기본 section
    python -m scripts.index_documents --strategy fixed_512_50
    python -m scripts.index_documents --strategy all  # 세 전략 모두
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml
import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

# from app.core.config import get_settings  # TODO(config): config 확정 후 주입

# --- 임시 상수 (TODO(config): D팀 config 키 확정 후 settings로 대체) ---
_CHROMA_PATH = str(Path(__file__).resolve().parent.parent / "chroma_db")
_COLLECTION_PREFIX = "safety_documents"           # settings.chroma_collection_name
_EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"  # settings.embedding_model
# --------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
_SOP_DIR = _ROOT / "data" / "sop"
_LAWS_DIR = _ROOT / "data" / "laws"

_EXCLUDE_FILES = {"rag_평가_질문셋.md"}

_STRATEGIES = ("section", "fixed_512_50", "fixed_1024_100")


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """마크다운 상단의 YAML front-matter와 본문을 분리한다."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    front_matter = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return front_matter, body


def split_sop_sections(body: str) -> list[tuple[str, str]]:
    """SOP 본문을 `##` 절 단위로 분할한다. 반환: [(섹션 제목, 내용), ...]"""
    sections: list[tuple[str, str]] = []
    chunks = re.split(r"\n(?=##\s)", body)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("##"):
            continue
        first_line, _, _ = chunk.partition("\n")
        section_title = first_line.lstrip("#").strip()
        sections.append((section_title, chunk))
    return sections


def split_fixed(text: str, size: int, overlap: int) -> list[str]:
    """텍스트를 고정 크기(size)로 자르되 overlap만큼 겹치게 분할한다."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    step = max(1, size - overlap)
    while start < len(text):
        chunks.append(text[start : start + size])
        start += step
    return chunks


def _fixed_params(strategy: str) -> tuple[int, int]:
    """전략 이름에서 (size, overlap)을 추출한다. 예: fixed_512_50 → (512, 50)"""
    m = re.match(r"fixed_(\d+)_(\d+)", strategy)
    if not m:
        raise ValueError(f"잘못된 고정 청킹 전략: {strategy}")
    return int(m.group(1)), int(m.group(2))


def build_sop_records(path: Path, strategy: str) -> list[dict[str, Any]]:
    """SOP 파일 하나를 청크 레코드 리스트로 변환한다."""
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    manual_id = meta.get("doc_id")
    records: list[dict[str, Any]] = []

    def _make(idx: int, section_title: str | None, content: str) -> dict[str, Any]:
        return {
            "id": f"{manual_id}__{strategy}__sec{idx}",
            "content": content,
            "metadata": {
                "source_id": meta.get("doc_id"),
                "document_type": meta.get("doc_type", "sop"),
                "title": section_title or manual_id,
                "section": section_title or "",
                "manual_id": manual_id,
                "machine_type": meta.get("machine_type"),
                "machine_id": meta.get("machine_id"),
                "manual_version": str(meta.get("version", "")),
            },
        }

    if strategy == "section":
        for idx, (section_title, content) in enumerate(split_sop_sections(body)):
            records.append(_make(idx, section_title, content))
    else:
        size, overlap = _fixed_params(strategy)
        # 고정 청킹은 절 경계를 무시하므로 section 메타는 소속 절 제목으로 근사한다.
        for idx, (section_title, content) in enumerate(split_sop_sections(body)):
            for j, piece in enumerate(split_fixed(content, size, overlap)):
                records.append(_make(f"{idx}_{j}", section_title, piece))
    return records


def build_law_records(path: Path, strategy: str) -> list[dict[str, Any]]:
    """법령 파일 하나를 청크 레코드 리스트로 변환한다.

    manual_id 리스트를 펼쳐 설비별로 복제 인덱싱한다.
    """
    text = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    source_id = meta.get("source_id") or meta.get("doc_id")
    manual_ids = meta.get("manual_id") or []
    if isinstance(manual_ids, str):
        manual_ids = [manual_ids]

    title = (
        f"{meta.get('law_name', '')} {meta.get('article', '')} "
        f"({meta.get('title', '')})"
    ).strip()

    # 전략별 본문 청크 조각 목록
    if strategy == "section":
        pieces = [body]
    else:
        size, overlap = _fixed_params(strategy)
        pieces = split_fixed(body, size, overlap)

    records: list[dict[str, Any]] = []
    for manual_id in manual_ids:
        for j, piece in enumerate(pieces):
            records.append(
                {
                    "id": f"{meta.get('doc_id')}__{manual_id}__{strategy}__{j}",
                    "content": piece,
                    "metadata": {
                        "source_id": source_id,
                        "document_type": meta.get("doc_type", "law"),
                        "title": title,
                        "section": meta.get("article"),
                        "manual_id": manual_id,
                        "law_name": meta.get("law_name"),
                        "article": meta.get("article"),
                        "manual_version": str(meta.get("law_version", "")),
                    },
                }
            )
    return records


def collect_records(strategy: str) -> list[dict[str, Any]]:
    """SOP·법령 폴더를 순회하며 모든 청크 레코드를 수집한다."""
    records: list[dict[str, Any]] = []
    for path in sorted(_SOP_DIR.glob("*.md")):
        if path.name in _EXCLUDE_FILES:
            print(f"[skip] {path.name} (평가 질문셋 제외)")
            continue
        records.extend(build_sop_records(path, strategy))
    for path in sorted(_LAWS_DIR.glob("*.md")):
        if path.name in _EXCLUDE_FILES:
            continue
        records.extend(build_law_records(path, strategy))
    return records


def index_one(strategy: str, embeddings: HuggingFaceEmbeddings,
              client: chromadb.PersistentClient) -> None:
    """단일 전략으로 인덱싱을 수행한다."""
    collection_name = f"{_COLLECTION_PREFIX}__{strategy}"
    try:
        client.delete_collection(collection_name)
        print(f"[reset] 기존 컬렉션 '{collection_name}' 삭제")
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    records = collect_records(strategy)
    if not records:
        print(f"[{strategy}] 인덱싱할 문서가 없습니다.")
        return

    ids = [r["id"] for r in records]
    contents = [r["content"] for r in records]
    metadatas = [r["metadata"] for r in records]
    vecs = embeddings.embed_documents(contents)

    collection.add(ids=ids, documents=contents, embeddings=vecs, metadatas=metadatas)

    sop_cnt = sum(1 for m in metadatas if m["document_type"] == "sop")
    law_cnt = sum(1 for m in metadatas if m["document_type"] == "law")
    print(f"[done] '{collection_name}' 총 {len(records)}개 청크 "
          f"(SOP {sop_cnt} / 법령 {law_cnt})")


def main() -> None:
    parser = argparse.ArgumentParser(description="문서 인덱싱 (청킹 전략 선택)")
    parser.add_argument(
        "--strategy",
        default="section",
        choices=(*_STRATEGIES, "all"),
        help="청킹 전략 (기본: section, 'all'이면 세 전략 모두)",
    )
    args = parser.parse_args()

    # TODO(config): 아래 상수들을 get_settings()로 대체
    embeddings = HuggingFaceEmbeddings(model_name=_EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=_CHROMA_PATH)

    targets = _STRATEGIES if args.strategy == "all" else (args.strategy,)
    for strategy in targets:
        index_one(strategy, embeddings, client)


if __name__ == "__main__":
    main()
