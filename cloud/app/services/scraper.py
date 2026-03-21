"""Web scraping service with caching, safety filtering, and HTML-to-text extraction."""
from __future__ import annotations

import ipaddress
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

MAX_RESPONSE_BYTES = 5_000_000       # 5 MB max download
MAX_TEXT_CHARS = 100_000             # 100K chars stored
REQUEST_TIMEOUT_S = 15               # per-request timeout
CACHE_TTL_S = 3600                   # 1 hour cache TTL
MAX_SEARCH_RESULTS = 5               # default search result pages to scrape
BLOCKED_DOMAINS: set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",
    "metadata.google.internal",
}


@dataclass
class ScrapeResult:
    text: str
    title: str
    byte_size: int
    truncated: bool


def _is_domain_allowed(url: str) -> bool:
    """Check if a URL's domain is safe to scrape."""
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    if hostname in BLOCKED_DOMAINS:
        return False

    # Check if hostname resolves to a private/loopback IP
    try:
        addr = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except socket.gaierror:
        # Can't resolve — allow the request (will fail at fetch time)
        pass

    return True


def scrape_url(url: str) -> ScrapeResult:
    """Fetch a URL and extract plain text using BeautifulSoup."""
    if not _is_domain_allowed(url):
        raise ValueError(f"Domain not allowed: {url}")

    from bs4 import BeautifulSoup

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HivemindScraper/2.0"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
        raw = resp.read(MAX_RESPONSE_BYTES)

    byte_size = len(raw)
    html = raw.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]

    return ScrapeResult(
        text=text,
        title=title,
        byte_size=byte_size,
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, ScrapeResult]] = {}


def scrape_url_cached(url: str) -> ScrapeResult:
    """Scrape with in-memory caching (TTL = CACHE_TTL_S)."""
    now = time.time()
    if url in _cache:
        ts, result = _cache[url]
        if now - ts < CACHE_TTL_S:
            return result

    result = scrape_url(url)
    _cache[url] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Search query scraping
# ---------------------------------------------------------------------------


def search_and_scrape(
    query: str,
    max_results: int = MAX_SEARCH_RESULTS,
) -> ScrapeResult:
    """Perform a DuckDuckGo search and scrape the top result pages.

    For each search result URL:
      1. Attempt to scrape the page using scrape_url_cached()
      2. If scraping fails, record the failure but continue
      3. Concatenate all scraped text, prefixed with source URLs

    Args:
        query: The search query string
        max_results: Maximum number of search result URLs to scrape (default 5)

    Returns:
        ScrapeResult with concatenated text from all scraped pages
    """
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))

    if not results:
        return ScrapeResult(
            text="No search results found.",
            title=f"Search: {query}",
            byte_size=0,
            truncated=False,
        )

    texts: list[str] = []
    total_bytes = 0

    for r in results:
        url = r.get("href", "")
        if not url:
            continue
        try:
            result = scrape_url_cached(url)
            texts.append(f"--- Source: {url} ---\n{result.text}")
            total_bytes += result.byte_size
        except Exception:
            texts.append(f"--- Source: {url} ---\n[Failed to fetch]")

    combined = "\n\n".join(texts)
    truncated = len(combined) > MAX_TEXT_CHARS
    if truncated:
        combined = combined[:MAX_TEXT_CHARS]

    return ScrapeResult(
        text=combined,
        title=f"Search: {query}",
        byte_size=total_bytes,
        truncated=truncated,
    )
