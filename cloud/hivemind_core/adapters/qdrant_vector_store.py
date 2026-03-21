"""Qdrant-based vector store adapter for Hivemind core."""
from __future__ import annotations

from typing import TYPE_CHECKING

from hivemind_core.types import RetrievedChunk, VectorStoreInterface

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class QdrantVectorStore(VectorStoreInterface):
    """Vector store adapter using Qdrant.

    This adapter bridges the Hivemind core to Qdrant for
    vector similarity search.
    """

    def __init__(
        self,
        qdrant_url: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        db: "Session | None" = None,
    ):
        self.qdrant_url = qdrant_url
        self.embedding_model = embedding_model
        self.db = db  # Optional: for fetching chunk metadata
        self._client = None
        self._encoder = None

    def _get_client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self.qdrant_url)
        return self._client

    def _get_encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(self.embedding_model)
        return self._encoder

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        encoder = self._get_encoder()
        embeddings = encoder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def retrieve(
        self,
        query: str,
        knowledge_base_ids: list[str],
        top_k: int = 8,
        similarity_threshold: float = 0.0,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks from knowledge bases.

        If *document_ids* is provided, only chunks whose payload ``document_id``
        is in the list are returned.
        """
        if not knowledge_base_ids:
            return []

        # Embed the query
        query_embedding = self._embed([query])[0]

        # Build an optional Qdrant filter for document_ids scoping
        query_filter = None
        if document_ids:
            try:
                from qdrant_client import models as qmodels

                query_filter = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchAny(any=document_ids),
                        ),
                    ]
                )
            except ImportError:
                # qdrant_client not available — fall back to post-filtering
                pass

        # Query each knowledge base collection
        all_results: list[tuple[str, float, dict]] = []
        client = self._get_client()
        # When filtering by document_ids, fetch more to compensate for filter
        search_limit = top_k * 5 if document_ids else top_k

        for kb_id in knowledge_base_ids:
            collection_name = f"kb_{kb_id}"
            try:
                results = client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=search_limit,
                )
                for hit in results:
                    all_results.append((str(hit.id), float(hit.score), hit.payload or {}))
            except Exception:
                # Collection might not exist
                continue

        # Always post-filter by document_ids when requested.
        # Even if a server-side MatchAny filter was sent, the post-filter is a
        # cheap safety net that guarantees correctness (including with mocks).
        if document_ids:
            doc_set = set(document_ids)
            all_results = [r for r in all_results if r[2].get("document_id") in doc_set]

        # Filter by threshold and sort
        filtered = [r for r in all_results if r[1] >= similarity_threshold]
        filtered.sort(key=lambda r: r[1], reverse=True)
        filtered = filtered[:top_k]

        # Convert to RetrievedChunk objects
        chunks: list[RetrievedChunk] = []

        # If we have a DB session, fetch full chunk data
        if self.db:
            chunk_ids = [r[0] for r in filtered]
            chunks = self._fetch_chunks_from_db(chunk_ids, filtered)
        else:
            # Use payload data only
            for chunk_id, score, payload in filtered:
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

    def _fetch_chunks_from_db(
        self,
        chunk_ids: list[str],
        results: list[tuple[str, float, dict]],
    ) -> list[RetrievedChunk]:
        """Fetch full chunk data from the database."""
        from app.models.knowledge_document import KnowledgeDocument
        from app.models.text_chunk import TextChunk

        if not chunk_ids:
            return []

        # Fetch chunks
        db_chunks = self.db.query(TextChunk).filter(TextChunk.id.in_(chunk_ids)).all()
        chunk_map = {chunk.id: chunk for chunk in db_chunks}

        # Fetch documents for filenames
        doc_ids = {chunk.document_id for chunk in db_chunks}
        documents = (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.id.in_(doc_ids))
            .all()
        )
        doc_map = {doc.id: doc for doc in documents}

        # Build results
        chunks: list[RetrievedChunk] = []
        for chunk_id, score, payload in results:
            db_chunk = chunk_map.get(chunk_id)
            if not db_chunk:
                continue

            doc = doc_map.get(db_chunk.document_id)
            chunks.append(
                RetrievedChunk(
                    id=db_chunk.id,
                    content=db_chunk.content,
                    score=score,
                    document_name=doc.filename if doc else "unknown",
                    source_page=db_chunk.source_page,
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
        """Upsert embeddings into a collection."""
        from qdrant_client.http.models import Distance, PointStruct, VectorParams

        client = self._get_client()

        # Ensure collection exists
        collections = {c.name for c in client.get_collections().collections}
        if collection not in collections:
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=len(embeddings[0]), distance=Distance.COSINE),
            )

        # Upsert points
        points = [
            PointStruct(id=ids[i], vector=embeddings[i], payload=payloads[i])
            for i in range(len(ids))
        ]
        client.upsert(collection_name=collection, points=points)
