"""Integration tests for agent CRUD endpoints."""
from __future__ import annotations


class TestAgentCRUD:
    def _create_agent(self, client, operator_headers, **overrides):
        payload = {
            "name": "Test Agent",
            "network_type": "theory",
            "description": "A test theory agent",
            "system_prompt": "You are a test agent.",
            "knowledge_base_ids": [],
            "rag_config": {"chunks_to_retrieve": 8, "similarity_threshold": 0.0, "use_reranking": False},
            "simulation_formula_ids": [],
            "status": "draft",
            **overrides,
        }
        return client.post("/agents", json=payload, headers=operator_headers)

    def test_create_agent(self, client, operator_headers):
        res = self._create_agent(client, operator_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Test Agent"
        assert data["network_type"] == "theory"
        assert "id" in data

    def test_list_agents_empty(self, client, operator_headers):
        res = client.get("/agents", headers=operator_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_agents_after_create(self, client, operator_headers):
        self._create_agent(client, operator_headers)
        res = client.get("/agents", headers=operator_headers)
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_get_agent_by_id(self, client, operator_headers):
        created = self._create_agent(client, operator_headers).json()
        res = client.get(f"/agents/{created['id']}", headers=operator_headers)
        assert res.status_code == 200
        assert res.json()["id"] == created["id"]

    def test_update_agent(self, client, operator_headers):
        created = self._create_agent(client, operator_headers).json()
        res = client.put(
            f"/agents/{created['id']}",
            json={"name": "Updated Agent"},
            headers=operator_headers,
        )
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Agent"

    def test_delete_agent(self, client, operator_headers):
        created = self._create_agent(client, operator_headers).json()
        res = client.delete(f"/agents/{created['id']}", headers=operator_headers)
        assert res.status_code == 200

        # Verify it's gone
        res = client.get(f"/agents/{created['id']}", headers=operator_headers)
        assert res.status_code == 404

    def test_get_nonexistent_agent(self, client, operator_headers):
        res = client.get("/agents/nonexistent-id", headers=operator_headers)
        assert res.status_code == 404
