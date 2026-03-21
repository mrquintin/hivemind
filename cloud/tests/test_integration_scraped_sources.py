"""Integration tests for scraped sources CRUD and scrape trigger endpoints."""
from __future__ import annotations

from unittest.mock import patch


class TestScrapedSourcesCRUD:

    def test_create_url_source(self, client, operator_headers):
        """POST /scraped-sources creates a source with status='pending'."""
        res = client.post(
            "/scraped-sources",
            json={"url_or_query": "https://example.com/article", "source_type": "url"},
            headers=operator_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["url_or_query"] == "https://example.com/article"
        assert data["source_type"] == "url"
        assert data["status"] == "pending"
        assert "id" in data

    def test_create_search_query_source(self, client, operator_headers):
        """POST /scraped-sources with source_type='search_query'."""
        res = client.post(
            "/scraped-sources",
            json={"url_or_query": "market trends 2026", "source_type": "search_query"},
            headers=operator_headers,
        )
        assert res.status_code == 200
        assert res.json()["source_type"] == "search_query"

    def test_list_sources_empty(self, client, operator_headers):
        """GET /scraped-sources returns empty list initially."""
        res = client.get("/scraped-sources", headers=operator_headers)
        assert res.status_code == 200
        assert res.json() == []

    def test_list_sources_after_create(self, client, operator_headers):
        """GET /scraped-sources returns created sources."""
        client.post(
            "/scraped-sources",
            json={"url_or_query": "https://example.com", "source_type": "url"},
            headers=operator_headers,
        )
        client.post(
            "/scraped-sources",
            json={"url_or_query": "https://other.com", "source_type": "url"},
            headers=operator_headers,
        )
        res = client.get("/scraped-sources", headers=operator_headers)
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_get_source_detail(self, client, operator_headers):
        """GET /scraped-sources/{id} returns detail with scraped_text field."""
        created = client.post(
            "/scraped-sources",
            json={"url_or_query": "https://example.com", "source_type": "url"},
            headers=operator_headers,
        ).json()
        res = client.get(f"/scraped-sources/{created['id']}", headers=operator_headers)
        assert res.status_code == 200
        detail = res.json()
        assert detail["url_or_query"] == "https://example.com"
        assert "scraped_text" in detail

    def test_get_nonexistent_source(self, client, operator_headers):
        """GET /scraped-sources/{bad_id} returns 404."""
        res = client.get("/scraped-sources/nonexistent-id", headers=operator_headers)
        assert res.status_code == 404

    def test_delete_source(self, client, operator_headers):
        """DELETE /scraped-sources/{id} removes the source."""
        created = client.post(
            "/scraped-sources",
            json={"url_or_query": "https://example.com", "source_type": "url"},
            headers=operator_headers,
        ).json()
        res = client.delete(f"/scraped-sources/{created['id']}", headers=operator_headers)
        assert res.status_code == 200
        # Verify deleted
        res = client.get(f"/scraped-sources/{created['id']}", headers=operator_headers)
        assert res.status_code == 404

    def test_delete_nonexistent_source(self, client, operator_headers):
        """DELETE /scraped-sources/{bad_id} returns 404."""
        res = client.delete("/scraped-sources/nonexistent-id", headers=operator_headers)
        assert res.status_code == 404

    def test_trigger_scrape_url(self, client, operator_headers):
        """POST /scraped-sources/{id}/scrape with mocked scraper."""
        created = client.post(
            "/scraped-sources",
            json={"url_or_query": "https://example.com", "source_type": "url"},
            headers=operator_headers,
        ).json()

        with patch("app.services.scraper.scrape_url_cached") as mock_scrape:
            from app.services.scraper import ScrapeResult
            mock_scrape.return_value = ScrapeResult(
                text="Scraped content here", title="Example", byte_size=500, truncated=False,
            )
            res = client.post(
                f"/scraped-sources/{created['id']}/scrape",
                headers=operator_headers,
            )
        assert res.status_code == 200
        assert res.json()["status"] == "completed"

        # Verify scraped_text was stored
        detail = client.get(f"/scraped-sources/{created['id']}", headers=operator_headers).json()
        assert detail["scraped_text"] == "Scraped content here"

    def test_trigger_scrape_failed(self, client, operator_headers):
        """Scrape failure sets status to 'failed' with error_message."""
        created = client.post(
            "/scraped-sources",
            json={"url_or_query": "https://bad.example.com", "source_type": "url"},
            headers=operator_headers,
        ).json()

        with patch("app.services.scraper.scrape_url_cached") as mock_scrape:
            mock_scrape.side_effect = Exception("Connection timeout")
            res = client.post(
                f"/scraped-sources/{created['id']}/scrape",
                headers=operator_headers,
            )
        assert res.status_code == 200
        assert res.json()["status"] == "failed"

        detail = client.get(f"/scraped-sources/{created['id']}", headers=operator_headers).json()
        assert "Connection timeout" in detail["error_message"]

    def test_trigger_scrape_nonexistent(self, client, operator_headers):
        """POST /scraped-sources/{bad_id}/scrape returns 404."""
        res = client.post("/scraped-sources/nonexistent-id/scrape", headers=operator_headers)
        assert res.status_code == 404

    def test_requires_auth(self, client):
        """Requests without token return 401 or 403."""
        res = client.get("/scraped-sources")
        assert res.status_code in (401, 403)

        res = client.post("/scraped-sources", json={"url_or_query": "https://x.com", "source_type": "url"})
        assert res.status_code in (401, 403)
