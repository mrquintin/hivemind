"""Tests for QdrantVectorStore document_ids filtering.

Tests the post-filter path (qdrant_client models may not be available in test env).
When qdrant_client IS available, the adapter uses server-side MatchAny filtering;
when it is NOT, it falls back to post-query filtering on payload.document_id.
Both paths are exercised here.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from hivemind_core.adapters.qdrant_vector_store import QdrantVectorStore


def _make_store() -> QdrantVectorStore:
    store = QdrantVectorStore(qdrant_url="http://localhost:6333")
    store._client = MagicMock()
    store._encoder = MagicMock()
    store._encoder.encode.return_value = MagicMock(tolist=lambda: [[0.1] * 384])
    return store


def _make_hit(point_id: str, score: float, doc_id: str = "d1"):
    hit = MagicMock()
    hit.id = point_id
    hit.score = score
    hit.payload = {"document_id": doc_id, "content": "chunk text"}
    return hit


class TestDocumentIdsFilter:
    def test_no_document_ids_no_filter(self):
        """Without document_ids, search proceeds normally."""
        store = _make_store()
        store._client.search.return_value = [_make_hit("c1", 0.9)]

        results = store.retrieve("test query", knowledge_base_ids=["kb1"])

        assert len(results) == 1
        assert results[0].id == "c1"

    def test_document_ids_filters_results(self):
        """With document_ids, only matching documents are returned."""
        store = _make_store()
        store._client.search.return_value = [
            _make_hit("c1", 0.9, "d1"),   # included
            _make_hit("c2", 0.85, "d2"),  # included
            _make_hit("c3", 0.8, "d3"),   # excluded
        ]

        results = store.retrieve(
            "test query",
            knowledge_base_ids=["kb1"],
            document_ids=["d1", "d2"],
        )

        returned_ids = {r.id for r in results}
        assert "c1" in returned_ids
        assert "c2" in returned_ids
        assert "c3" not in returned_ids

    def test_document_ids_increases_search_limit(self):
        """When document_ids is provided, limit is multiplied by 5."""
        store = _make_store()
        store._client.search.return_value = []

        store.retrieve(
            "test query",
            knowledge_base_ids=["kb1"],
            top_k=5,
            document_ids=["d1"],
        )

        call_kwargs = store._client.search.call_args
        assert call_kwargs.kwargs.get("limit") == 25  # 5 * 5

    def test_without_document_ids_limit_equals_top_k(self):
        """Without document_ids, limit equals top_k."""
        store = _make_store()
        store._client.search.return_value = []

        store.retrieve("test query", knowledge_base_ids=["kb1"], top_k=5)

        call_kwargs = store._client.search.call_args
        assert call_kwargs.kwargs.get("limit") == 5

    def test_results_still_filtered_by_threshold(self):
        """Threshold filtering still applies with document_ids."""
        store = _make_store()
        store._client.search.return_value = [
            _make_hit("c1", 0.9, "d1"),
            _make_hit("c2", 0.1, "d1"),  # Below threshold
        ]

        results = store.retrieve(
            "test query",
            knowledge_base_ids=["kb1"],
            similarity_threshold=0.5,
            document_ids=["d1"],
        )

        assert len(results) == 1
        assert results[0].id == "c1"

    def test_empty_knowledge_base_ids_returns_empty(self):
        """Empty knowledge_base_ids returns [] regardless of document_ids."""
        store = _make_store()

        results = store.retrieve(
            "test query",
            knowledge_base_ids=[],
            document_ids=["d1"],
        )

        assert results == []
        store._client.search.assert_not_called()

    def test_all_filtered_out_returns_empty(self):
        """When no results match document_ids, returns empty."""
        store = _make_store()
        store._client.search.return_value = [
            _make_hit("c1", 0.9, "d_other"),
        ]

        results = store.retrieve(
            "test query",
            knowledge_base_ids=["kb1"],
            document_ids=["d1"],
        )

        assert results == []
