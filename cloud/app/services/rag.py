from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.knowledge_document import KnowledgeDocument
from app.models.text_chunk import TextChunk
from app.rag.retrieval import retrieve


def retrieve_chunks(
    db: Session,
    query: str,
    knowledge_base_ids: list[str],
    rag_config: dict | None = None,
) -> list[dict]:
    if not knowledge_base_ids:
        return []

    rag_config = rag_config or {}
    top_k = rag_config.get("chunks_to_retrieve", settings.RAG_TOP_K)
    similarity_threshold = rag_config.get(
        "similarity_threshold", settings.RAG_SIMILARITY_THRESHOLD
    )

    results = retrieve(query, knowledge_base_ids, top_k=top_k, similarity_threshold=similarity_threshold)

    chunk_ids = [chunk_id for chunk_id, _, _ in results]
    if not chunk_ids:
        return []

    chunks = (
        db.query(TextChunk)
        .filter(TextChunk.id.in_(chunk_ids))
        .all()
    )
    chunk_map = {chunk.id: chunk for chunk in chunks}

    document_ids = {chunk.document_id for chunk in chunks}
    documents = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id.in_(document_ids))
        .all()
    )
    document_map = {doc.id: doc for doc in documents}

    formatted: list[dict] = []
    for chunk_id, score, payload in results:
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue
        document = document_map.get(chunk.document_id)
        formatted.append(
            {
                "id": chunk.id,
                "content": chunk.content,
                "score": score,
                "document_name": document.filename if document else "unknown",
                "source_page": chunk.source_page,
                "payload": payload,
            }
        )
    return formatted
