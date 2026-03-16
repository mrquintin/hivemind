from __future__ import annotations

from app.config import settings
from app.rag.embeddings import embed_texts
from app.rag.vector_store import query_embeddings


def retrieve(
    query: str,
    knowledge_base_ids: list[str],
    top_k: int | None = None,
    similarity_threshold: float | None = None,
) -> list[tuple[str, float, dict]]:
    if not knowledge_base_ids:
        return []

    top_k = top_k or settings.RAG_TOP_K
    similarity_threshold = (
        settings.RAG_SIMILARITY_THRESHOLD
        if similarity_threshold is None
        else similarity_threshold
    )

    query_embedding = embed_texts([query])[0]
    results: list[tuple[str, float, dict]] = []
    for kb_id in knowledge_base_ids:
        collection = f"kb_{kb_id}"
        results.extend(query_embeddings(collection, query_embedding, top_k))

    filtered = [r for r in results if r[1] >= similarity_threshold]
    filtered.sort(key=lambda r: r[1], reverse=True)
    return filtered[:top_k]
