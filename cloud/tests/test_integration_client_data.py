"""Integration tests for client data CRUD endpoints."""
from __future__ import annotations

from unittest.mock import patch

CLIENT_ID = "testuser"


class TestClientDataCRUD:
    def test_create_client_data(self, client, operator_headers):
        res = client.post(
            f"/clients/{CLIENT_ID}/data",
            json={"label": "Q4 Report", "content": "Revenue was $10M", "metadata": {}},
            headers=operator_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["label"] == "Q4 Report"
        assert data["content"] == "Revenue was $10M"
        assert data["client_id"] == CLIENT_ID

    def test_list_client_data_empty(self, client, operator_headers):
        res = client.get(f"/clients/{CLIENT_ID}/data", headers=operator_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_client_data_after_create(self, client, operator_headers):
        client.post(
            f"/clients/{CLIENT_ID}/data",
            json={"label": "Entry 1", "content": "Content 1", "metadata": {}},
            headers=operator_headers,
        )
        client.post(
            f"/clients/{CLIENT_ID}/data",
            json={"label": "Entry 2", "content": "Content 2", "metadata": {}},
            headers=operator_headers,
        )
        res = client.get(f"/clients/{CLIENT_ID}/data", headers=operator_headers)
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_get_client_data_by_id(self, client, operator_headers):
        created = client.post(
            f"/clients/{CLIENT_ID}/data",
            json={"label": "Specific", "content": "Specific content", "metadata": {}},
            headers=operator_headers,
        ).json()
        res = client.get(
            f"/clients/{CLIENT_ID}/data/{created['id']}",
            headers=operator_headers,
        )
        assert res.status_code == 200
        assert res.json()["label"] == "Specific"

    def test_delete_client_data(self, client, operator_headers):
        created = client.post(
            f"/clients/{CLIENT_ID}/data",
            json={"label": "To Delete", "content": "Delete me", "metadata": {}},
            headers=operator_headers,
        ).json()
        res = client.delete(
            f"/clients/{CLIENT_ID}/data/{created['id']}",
            headers=operator_headers,
        )
        assert res.status_code == 200

        # Verify deleted
        res = client.get(
            f"/clients/{CLIENT_ID}/data/{created['id']}",
            headers=operator_headers,
        )
        assert res.status_code == 404

    def test_get_nonexistent_data(self, client, operator_headers):
        res = client.get(
            f"/clients/{CLIENT_ID}/data/nonexistent-id",
            headers=operator_headers,
        )
        assert res.status_code == 404

    def test_upload_file(self, client, operator_headers):
        """POST /clients/{id}/data/upload creates entry from file."""
        with patch("app.rag.extraction.extract_text_from_bytes") as mock_extract, \
             patch("app.services.storage.store_file") as mock_store:
            mock_extract.return_value = "Extracted text content from the PDF"
            mock_store.return_value = ("uploads/test.pdf", 1024)

            res = client.post(
                f"/clients/{CLIENT_ID}/data/upload",
                files={"file": ("report.pdf", b"fake pdf content", "application/pdf")},
                headers=operator_headers,
            )

        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "Extracted text content from the PDF"
        assert data["client_id"] == CLIENT_ID

    def test_requires_auth(self, client):
        res = client.get(f"/clients/{CLIENT_ID}/data")
        assert res.status_code in (401, 403)

    def test_client_role_cannot_access_other_client_id(self, client, client_headers):
        res = client.get(f"/clients/{CLIENT_ID}/data", headers=client_headers)
        assert res.status_code == 403

    def test_client_role_can_create_and_list_own_data(self, client, client_headers):
        own_id = "client-1"
        create_res = client.post(
            f"/clients/{own_id}/data",
            json={"label": "Owned", "content": "My data", "metadata": {}},
            headers=client_headers,
        )
        assert create_res.status_code == 200

        list_res = client.get(f"/clients/{own_id}/data", headers=client_headers)
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1
