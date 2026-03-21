"""Tests for the web scraping service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.scraper import (
    CACHE_TTL_S,
    MAX_TEXT_CHARS,
    ScrapeResult,
    _cache,
    _is_domain_allowed,
    scrape_url,
    scrape_url_cached,
)

SAMPLE_HTML = b"""<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<nav>Navigation</nav>
<header>Header content</header>
<script>var x = 1;</script>
<style>body { color: red; }</style>
<main>
  <h1>Hello World</h1>
  <p>This is the main content.</p>
</main>
<footer>Footer content</footer>
</body>
</html>"""


class TestIsDomainAllowed:
    def test_blocks_localhost(self):
        assert not _is_domain_allowed("http://localhost:8000/page")

    def test_blocks_127_0_0_1(self):
        assert not _is_domain_allowed("http://127.0.0.1/page")

    def test_blocks_metadata_endpoint(self):
        assert not _is_domain_allowed("http://169.254.169.254/latest/meta-data")

    def test_blocks_ftp_scheme(self):
        assert not _is_domain_allowed("ftp://example.com/file")

    def test_blocks_no_scheme(self):
        assert not _is_domain_allowed("example.com/page")

    def test_allows_http(self):
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            assert _is_domain_allowed("http://example.com/page")

    def test_allows_https(self):
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            assert _is_domain_allowed("https://example.com/page")

    @patch("socket.gethostbyname", return_value="10.0.0.1")
    def test_blocks_private_ip(self, mock_dns):
        assert not _is_domain_allowed("http://internal.corp.com/page")

    @patch("socket.gethostbyname", return_value="127.0.0.1")
    def test_blocks_loopback_ip(self, mock_dns):
        assert not _is_domain_allowed("http://sneaky.example.com/page")


class TestScrapeUrl:
    @patch("urllib.request.urlopen")
    def test_extracts_text_and_title(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_HTML
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            result = scrape_url("http://example.com")

        assert result.title == "Test Page"
        assert "Hello World" in result.text
        assert "This is the main content." in result.text
        # Scripts, styles, nav, footer, header should be removed
        assert "var x = 1" not in result.text
        assert "Navigation" not in result.text
        assert "Footer content" not in result.text
        assert "Header content" not in result.text
        assert result.byte_size == len(SAMPLE_HTML)
        assert not result.truncated

    @patch("urllib.request.urlopen")
    def test_truncates_long_text(self, mock_urlopen):
        long_text = "A" * (MAX_TEXT_CHARS + 1000)
        html = f"<html><body><p>{long_text}</p></body></html>".encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            result = scrape_url("http://example.com")

        assert result.truncated
        assert len(result.text) == MAX_TEXT_CHARS

    def test_blocked_domain_raises(self):
        with pytest.raises(ValueError, match="Domain not allowed"):
            scrape_url("http://localhost:8000/page")

    def test_blocked_scheme_raises(self):
        with pytest.raises(ValueError, match="Domain not allowed"):
            scrape_url("ftp://example.com/file")

    @patch("urllib.request.urlopen")
    def test_passes_timeout(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body>OK</body></html>"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            scrape_url("http://example.com")

        _, kwargs = mock_urlopen.call_args
        assert kwargs["timeout"] == 15


class TestScrapeUrlCached:
    def setup_method(self):
        _cache.clear()

    @patch("app.services.scraper.scrape_url")
    def test_caches_result(self, mock_scrape):
        mock_scrape.return_value = ScrapeResult(
            text="cached", title="T", byte_size=100, truncated=False
        )

        r1 = scrape_url_cached("http://example.com")
        r2 = scrape_url_cached("http://example.com")

        assert mock_scrape.call_count == 1
        assert r1.text == "cached"
        assert r2.text == "cached"

    @patch("app.services.scraper.scrape_url")
    def test_expires_after_ttl(self, mock_scrape):
        mock_scrape.return_value = ScrapeResult(
            text="v1", title="T", byte_size=100, truncated=False
        )
        scrape_url_cached("http://example.com")

        # Manually expire
        url = "http://example.com"
        ts, result = _cache[url]
        _cache[url] = (ts - CACHE_TTL_S - 1, result)

        mock_scrape.return_value = ScrapeResult(
            text="v2", title="T", byte_size=100, truncated=False
        )
        r = scrape_url_cached("http://example.com")

        assert mock_scrape.call_count == 2
        assert r.text == "v2"


class TestSearchAndScrape:
    def setup_method(self):
        _cache.clear()

    @patch("app.services.scraper.scrape_url_cached")
    @patch("duckduckgo_search.DDGS")
    def test_basic_search(self, MockDDGS, mock_scrape_cached):
        """Search returns concatenated text from scraped result pages."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"href": "https://example.com/page1", "title": "Page 1"},
            {"href": "https://example.com/page2", "title": "Page 2"},
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        mock_scrape_cached.side_effect = [
            ScrapeResult(text="Content from page 1", title="P1", byte_size=200, truncated=False),
            ScrapeResult(text="Content from page 2", title="P2", byte_size=300, truncated=False),
        ]

        result = search_and_scrape("market trends")

        assert result.title == "Search: market trends"
        assert "Content from page 1" in result.text
        assert "Content from page 2" in result.text
        assert "--- Source: https://example.com/page1 ---" in result.text
        assert "--- Source: https://example.com/page2 ---" in result.text
        assert result.byte_size == 500
        assert not result.truncated

    @patch("app.services.scraper.scrape_url_cached")
    @patch("duckduckgo_search.DDGS")
    def test_failed_url_handled_gracefully(self, MockDDGS, mock_scrape_cached):
        """Failed scrapes are recorded as '[Failed to fetch]'."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"href": "https://good.com", "title": "Good"},
            {"href": "https://bad.com", "title": "Bad"},
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        mock_scrape_cached.side_effect = [
            ScrapeResult(text="Good content", title="Good", byte_size=100, truncated=False),
            Exception("Connection refused"),
        ]

        result = search_and_scrape("test query")

        assert "Good content" in result.text
        assert "[Failed to fetch]" in result.text
        assert "--- Source: https://bad.com ---" in result.text

    @patch("duckduckgo_search.DDGS")
    def test_no_results(self, MockDDGS):
        """Empty search results return a meaningful message."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        result = search_and_scrape("extremely obscure query xyz123")

        assert result.text == "No search results found."
        assert result.byte_size == 0

    @patch("app.services.scraper.scrape_url_cached")
    @patch("duckduckgo_search.DDGS")
    def test_truncation(self, MockDDGS, mock_scrape_cached):
        """Combined text exceeding MAX_TEXT_CHARS is truncated."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"href": "https://example.com/long", "title": "Long"},
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        long_text = "A" * (MAX_TEXT_CHARS + 1000)
        mock_scrape_cached.return_value = ScrapeResult(
            text=long_text, title="Long", byte_size=len(long_text), truncated=False,
        )

        result = search_and_scrape("long content query")

        assert result.truncated
        assert len(result.text) == MAX_TEXT_CHARS

    @patch("app.services.scraper.scrape_url_cached")
    @patch("duckduckgo_search.DDGS")
    def test_max_results_passed(self, MockDDGS, mock_scrape_cached):
        """The max_results parameter is passed to DDGS.text()."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = []
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        search_and_scrape("test", max_results=3)

        mock_ddgs_instance.text.assert_called_once_with("test", max_results=3)

    @patch("app.services.scraper.scrape_url_cached")
    @patch("duckduckgo_search.DDGS")
    def test_skips_empty_hrefs(self, MockDDGS, mock_scrape_cached):
        """Search results without 'href' are skipped."""
        from app.services.scraper import search_and_scrape

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"href": "", "title": "Empty"},
            {"title": "No href key"},
            {"href": "https://valid.com", "title": "Valid"},
        ]
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        MockDDGS.return_value = mock_ddgs_instance

        mock_scrape_cached.return_value = ScrapeResult(
            text="Valid content", title="Valid", byte_size=100, truncated=False,
        )

        result = search_and_scrape("test")

        mock_scrape_cached.assert_called_once_with("https://valid.com")
        assert "Valid content" in result.text
