"""Chroma 기반 Vector DB 어댑터.

rag_service.VectorStore 프로토콜을 구현한다.
설비별 SOP·법령·KOSHA 문서가 적재된 Chroma 컬렉션에 대해
메타데이터 필터 기반 유사도 검색을 수행한다.

민감정보(DB 경로, 임베딩 모델명 등)는 원래 core.config로 주입받아야 하나,
현재 config 키가 미확정이므로 임시 상수로 대체한다. (TODO(config) 참고)
"""

from __future__ import annotations

from typing import Any

import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

# from app.core.config import get_settings  # TODO(config): config 확정 후 주입

# --- 임시 상수 (TODO(config): D팀 config 키 확정 후 아래 상수 제거하고 settings로 대체) ---
# settings.chroma_path 로 대체 예정
_CHROMA_PATH = "./chroma_db"
# settings.chroma_collection_name 으로 대체 예정
_COLLECTION_NAME = "safety_documents"
# settings.embedding_model 로 대체 예정
_EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"
# -------------------------------------------------------------------------


class ChromaVectorStore:
    """Chroma PersistentClient를 감싼 Vector DB 어댑터.

    rag_service.VectorStore 프로토콜(query 메서드)을 만족한다.
    """

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str | None = None,
        embedding_model: str | None = None,
    ) -> None:
        # TODO(config): 인자가 없으면 get_settings()에서 값을 읽도록 변경
        # settings = get_settings()
        self._chroma_path = chroma_path or _CHROMA_PATH
        self._collection_name = collection_name or _COLLECTION_NAME
        self._embedding_model_name = embedding_model or _EMBEDDING_MODEL

        self._embeddings = HuggingFaceEmbeddings(
            model_name=self._embedding_model_name,
        )
        self._client = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
        )

    def query(
        self,
        query_text: str,
        top_k: int,
        metadata_filter: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """query_text에 대해 top_k개의 청크를 검색한다.

        각 결과는 rag_service가 기대하는 키를 포함해 반환한다:
        source_id, document_type, title, section, content,
        relevance_score, manual_version.
        """
        query_embedding = self._embeddings.embed_query(query_text)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=metadata_filter or None,
        )

        return self._to_documents(results)

    @staticmethod
    def _to_documents(results: dict[str, Any]) -> list[dict[str, Any]]:
        """Chroma 원시 응답을 rag_service 공통 형식으로 변환한다.

        Chroma query 결과는 각 필드가 배치(list of list) 형태이므로
        첫 번째 쿼리([0])에 대한 결과만 사용한다.
        거리(distance)는 유사도 점수(relevance_score)로 변환한다.
        """
        documents: list[dict[str, Any]] = []

        # 결과가 비어 있으면 빈 리스트 반환
        ids = results.get("ids") or [[]]
        if not ids or not ids[0]:
            return documents

        metadatas = (results.get("metadatas") or [[]])[0]
        contents = (results.get("documents") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        for meta, content, distance in zip(metadatas, contents, distances):
            meta = meta or {}
            documents.append(
                {
                    "source_id": meta.get("source_id"),
                    "document_type": meta.get("document_type"),
                    "title": meta.get("title"),
                    "section": meta.get("section"),
                    "content": content,
                    # 코사인 거리 → 유사도(1 - distance). 음수 방지를 위해 max 처리.
                    "relevance_score": _distance_to_score(distance),
                    "manual_version": meta.get("manual_version"),
                }
            )
        return documents


def _distance_to_score(distance: float | None) -> float | None:
    """Chroma 거리 값을 0~1 유사도 점수로 변환한다.

    코사인 거리 기준 score = 1 - distance. distance가 없으면 None.
    """
    if distance is None:
        return None
    return max(0.0, 1.0 - distance)
