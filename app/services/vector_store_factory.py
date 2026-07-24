"""Vector store 팩토리.

구체 구현(Chroma 등)을 config 기반으로 생성해 rag_agent에 주입한다.
경로·모델명 등 민감/환경 의존 값은 core.config에서만 읽는다.
"""

from __future__ import annotations

from functools import lru_cache

from app.services.rag_service import VectorStore


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """설정에 따라 Vector store 인스턴스를 생성해 반환한다(싱글턴).

    실제 Chroma 어댑터 구현은 vector_store_chroma 모듈에 위치한다.
    """
    from app.services.vector_store_chroma import ChromaVectorStore

    return ChromaVectorStore()
