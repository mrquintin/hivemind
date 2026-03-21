"""Integration tests for knowledge bases CRUD and upload-text endpoints."""
from __future__ import annotations

from unittest.mock import patch


class TestKnowledgeBasesCRUD:

    def test_create_knowledge_base(self, client, operator_headers):
        res = client.post(
            "/knowledge-bases",
            json={"name": "Market Entry Frameworks", "description": "Strategies for entering new markets"},
            headers=operator_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Market Entry Frameworks"
        assert "id" in data

    def test_list_knowledge_bases_empty(self, client, operator_headers):
        res = client.get("/knowledge-bases", headers=operator_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_knowledge_bases_after_create(self, client, operator_headers):
        client.post(
            "/knowledge-bases",
            json={"name": "KB One"},
            headers=operator_headers,
        )
        client.post(
            "/knowledge-bases",
            json={"name": "KB Two"},
            headers=operator_headers,
        )
        res = client.get("/knowledge-bases", headers=operator_headers)
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_get_knowledge_base(self, client, operator_headers):
        created = client.post(
            "/knowledge-bases",
            json={"name": "Test KB", "description": "A test knowledge base"},
            headers=operator_headers,
        ).json()
        res = client.get(f"/knowledge-bases/{created['id']}", headers=operator_headers)
        assert res.status_code == 200
        assert res.json()["name"] == "Test KB"

    def test_get_nonexistent_kb(self, client, operator_headers):
        res = client.get("/knowledge-bases/nonexistent-id", headers=operator_headers)
        assert res.status_code == 404

    def test_delete_knowledge_base(self, client, operator_headers):
        created = client.post(
            "/knowledge-bases",
            json={"name": "To Delete"},
            headers=operator_headers,
        ).json()
        res = client.delete(f"/knowledge-bases/{created['id']}", headers=operator_headers)
        assert res.status_code == 200
        # Verify deleted
        res = client.get(f"/knowledge-bases/{created['id']}", headers=operator_headers)
        assert res.status_code == 404

    def test_delete_nonexistent_kb(self, client, operator_headers):
        res = client.delete("/knowledge-bases/nonexistent-id", headers=operator_headers)
        assert res.status_code == 404

    def test_upload_text(self, client, operator_headers):
        """POST /{id}/upload-text creates a document from pasted text."""
        created = client.post(
            "/knowledge-bases",
            json={"name": "Text Upload KB"},
            headers=operator_headers,
        ).json()
        kb_id = created["id"]

        with patch("app.routers.knowledge_bases.store_file") as mock_store, \
             patch("app.routers.knowledge_bases.get_active_api_key") as mock_key, \
             patch("app.routers.knowledge_bases.optimize_document") as mock_optimize, \
             patch("app.routers.knowledge_bases.chunk_text") as mock_chunk, \
             patch("app.routers.knowledge_bases.embed_texts") as mock_embed, \
             patch("app.routers.knowledge_bases.upsert_embeddings") as mock_upsert:
            mock_store.return_value = ("uploads/test.txt", 100)
            mock_key.return_value = "test-key"
            mock_optimize.return_value = None  # No optimization
            mock_chunk.return_value = [("chunk one", 10)]
            mock_embed.return_value = [[0.1] * 384]
            mock_upsert.return_value = None

            res = client.post(
                f"/knowledge-bases/{kb_id}/upload-text",
                json={
                    "title": "Test Framework",
                    "content": "This is a strategic framework for market analysis with enough text to pass validation.",
                },
                headers=operator_headers,
            )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "processed"
        assert data["document_type"] == "framework"
        assert "document_id" in data

    def test_upload_text_to_nonexistent_kb(self, client, operator_headers):
        with patch("app.routers.knowledge_bases.store_file"), \
             patch("app.routers.knowledge_bases.get_active_api_key"), \
             patch("app.routers.knowledge_bases.optimize_document"):
            res = client.post(
                "/knowledge-bases/nonexistent-id/upload-text",
                json={"title": "Test", "content": "Some content that is long enough to pass validation checks."},
                headers=operator_headers,
            )
        assert res.status_code == 404

    def test_upload_text_too_short(self, client, operator_headers):
        created = client.post(
            "/knowledge-bases",
            json={"name": "Short Text KB"},
            headers=operator_headers,
        ).json()
        res = client.post(
            f"/knowledge-bases/{created['id']}/upload-text",
            json={"title": "Test", "content": "Short"},
            headers=operator_headers,
        )
        assert res.status_code == 400

    def test_requires_auth(self, client):
        res = client.get("/knowledge-bases")
        assert res.status_code in (401, 403)

        res = client.post("/knowledge-bases", json={"name": "Unauthorized"})
        assert res.status_code in (401, 403)
