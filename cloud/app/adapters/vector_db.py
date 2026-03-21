"""
Qdrant vector database adapter implementing Hivemind Core VectorStoreInterface.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.rag.embeddings import embed_texts
from app.rag.vector_store import query_embeddings
from hivemind_core.types import RetrievedChunk, VectorStoreInterface


class QdrantVectorDB(VectorStoreInterface):
    """Qdrant implementation of VectorStoreInterface."""

    def __init__(self, url: str | None = None):
        self.url = url or settings.VECTOR_DB_URL

    def retrieve(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int = 8,
        similarity_threshold: float = 0.0,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks from knowledge bases.

        Args:
            query: The query text to search for
            knowledge_base_ids: List of knowledge base IDs to search
            top_k: Maximum number of results to return
            similarity_threshold: Minimum similarity score threshold
            document_ids: If set, only return chunks from these document IDs (post-filter).

        Returns:
            List of RetrievedChunk objects sorted by relevance
        """
        if not knowledge_base_ids:
            return []

        # When filtering by document_ids, request more results so we have enough after filter
        fetch_k = (top_k * 5) if document_ids else top_k

        # Generate query embedding
        query_embeddings_list = embed_texts([query])
        if not query_embeddings_list:
            return []
        query_embedding = query_embeddings_list[0]

        # Query each knowledge base collection
        all_results: list[tuple[str, float, dict[str, Any]]] = []
        for kb_id in knowledge_base_ids:
            collection = f"kb_{kb_id}"
            try:
                kb_results = query_embeddings(collection, query_embedding, fetch_k)
                all_results.extend(kb_results)
            except Exception:
                # Collection might not exist yet
                pass

        # Filter by threshold
        filtered = [r for r in all_results if r[1] >= similarity_threshold]

        # Post-filter by document_id when requested
        if document_ids:
            doc_set = set(document_ids)
            filtered = [r for r in filtered if (r[2] or {}).get("document_id") in doc_set]

        # Sort by score descending and limit
        filtered.sort(key=lambda r: r[1], reverse=True)
        limited = filtered[:top_k]

        # Convert to RetrievedChunk objects
        chunks: list[RetrievedChunk] = []
        for chunk_id, score, payload in limited:
            chunks.append(
                RetrievedChunk(
                    id=chunk_id,
                    content=payload.get("content", ""),
                    score=score,
                    document_name=payload.get("document_name", "unknown"),
                    source_page=payload.get("source_page"),
                    metadata=payload,
                )
            )

        return chunks

    def upsert(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict],
    ) -> None:
        """Upsert vectors into the vector store.

        This method is called when indexing documents.
        The actual implementation is handled by app.rag.vector_store.
        """
        # Import here to avoid circular imports
        from app.rag.vector_store import upsert_embeddings
        upsert_embeddings(collection, ids, embeddings, payloads)
