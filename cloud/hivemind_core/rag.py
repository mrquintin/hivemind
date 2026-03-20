"""RAG (Retrieval-Augmented Generation) utilities for Hivemind core.

Provides retrieval and formatting of knowledge chunks for injection
into agent prompts.
"""
from __future__ import annotations

from hivemind_core.types import RagConfig, RetrievedChunk, VectorStoreInterface


def retrieve_chunks(
    vector_store: VectorStoreInterface,
    query: str,
    knowledge_base_ids: list[str],
    rag_config: RagConfig | dict | None = None,
    document_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve relevant chunks from knowledge bases.

    Args:
        vector_store: Vector store implementation
        query: The query to search for
        knowledge_base_ids: IDs of knowledge bases to search
        rag_config: RAG configuration (chunks to retrieve, threshold, etc.)
        document_ids: Optional list of document IDs to restrict retrieval to.

    Returns:
        List of retrieved chunks sorted by relevance
    """
    if not knowledge_base_ids:
        return []

    # Normalize rag_config
    if rag_config is None:
        config = RagConfig()
    elif isinstance(rag_config, dict):
        config = RagConfig(
            chunks_to_retrieve=rag_config.get("chunks_to_retrieve", 8),
            similarity_threshold=rag_config.get("similarity_threshold", 0.0),
            use_reranking=rag_config.get("use_reranking", False),
        )
    else:
        config = rag_config

    return vector_store.retrieve(
        query=query,
        knowledge_base_ids=knowledge_base_ids,
        top_k=config.chunks_to_retrieve,
        similarity_threshold=config.similarity_threshold,
        document_ids=document_ids or None,
    )


def format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks for inclusion in an agent's system prompt.

    Args:
        chunks: List of retrieved chunks

    Returns:
        Formatted string for prompt injection
    """
    if not chunks:
        return "No retrieved knowledge for this query."

    lines = []
    for idx, chunk in enumerate(chunks, start=1):
        # Handle both dataclass and dict-like structures
        if isinstance(chunk, dict):
            doc_name = chunk.get("document_name", "unknown")
            source_page = chunk.get("source_page")
            content = chunk.get("content", "")
        else:
            doc_name = chunk.document_name
            source_page = chunk.source_page
            content = chunk.content

        page = f"p. {source_page}" if source_page else "page n/a"
        lines.append(f"[EXCERPT {idx}] {doc_name} ({page})\n{content}")

    return "\n\n".join(lines)
