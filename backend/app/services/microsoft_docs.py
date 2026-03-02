"""Microsoft Learn documentation search service.

Searches the public Microsoft Learn API for relevant documentation
and extracts content to provide as additional context for reply generation.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings
from ingestion.utils import extract_html_text

logger = logging.getLogger(__name__)

SEARCH_URL = "https://learn.microsoft.com/api/search"
REQUEST_TIMEOUT = 10.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_CONTENT_CHARS = 3000  # max chars per article to include as context
CACHE_TTL_SECONDS = 300  # 5 minutes
MAX_CACHE_ENTRIES = 128  # evict oldest entries when exceeded
ALLOWED_ARTICLE_DOMAIN = "learn.microsoft.com"


@dataclass
class WebContextDoc:
    title: str
    url: str
    content: str


# Simple in-memory cache: {cache_key: (timestamp, results)}
# Uses asyncio.Lock since all access is from the async event loop.
_cache: dict[str, tuple[float, list[WebContextDoc]]] = {}
_cache_lock = asyncio.Lock()


def _cache_key(keywords: str) -> str:
    return hashlib.sha256(keywords.lower().strip().encode()).hexdigest()


async def _get_cached(keywords: str) -> list[WebContextDoc] | None:
    async with _cache_lock:
        key = _cache_key(keywords)
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, docs = entry
        if time.monotonic() - ts > CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return docs


async def _set_cached(keywords: str, docs: list[WebContextDoc]) -> None:
    async with _cache_lock:
        # Evict oldest entries when cache exceeds max size
        if len(_cache) >= MAX_CACHE_ENTRIES:
            oldest_key = min(_cache, key=lambda k: _cache[k][0])
            del _cache[oldest_key]
        _cache[_cache_key(keywords)] = (time.monotonic(), docs)


class MicrosoftDocsService:
    """Searches Microsoft Learn for relevant documentation using a shared async httpx client."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def search(self, keywords: str) -> list[WebContextDoc]:
        """Search Microsoft Learn and extract article content.

        Returns empty list on any failure (graceful degradation).
        """
        if not settings.microsoft_docs_enabled:
            return []

        if not keywords.strip():
            return []

        cached = await _get_cached(keywords)
        if cached is not None:
            logger.debug("MS Docs cache hit for: %s", keywords[:60])
            return cached

        try:
            results = await self._do_search(keywords)
            await _set_cached(keywords, results)
            return results
        except Exception:
            logger.warning("Microsoft Learn search failed for: %s", keywords[:60], exc_info=True)
            return []

    async def _do_search(self, keywords: str) -> list[WebContextDoc]:
        """Execute search API call and fetch top articles."""
        search_results = await self._search_api(keywords)
        if not search_results:
            return []

        # Fetch articles in parallel (up to 3)
        tasks = [self._fetch_article(url) for _, url in search_results[:3]]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        docs: list[WebContextDoc] = []
        for i, result in enumerate(fetched):
            if isinstance(result, Exception):
                logger.debug("Failed to fetch article %s: %s", search_results[i][1], result)
                continue
            if not isinstance(result, str) or not result:
                continue
            title = search_results[i][0]
            docs.append(WebContextDoc(
                title=title,
                url=search_results[i][1],
                content=result[:MAX_CONTENT_CHARS],
            ))
        return docs

    async def _search_api(self, keywords: str) -> list[tuple[str, str]]:
        """Call Microsoft Learn search API. Returns [(title, url), ...]."""
        try:
            resp = await self._client.get(
                SEARCH_URL,
                params={"search": keywords, "locale": "en-us", "$top": "3"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            results: list[tuple[str, str]] = []
            for item in data.get("results", []):
                title = item.get("title", "")
                url = item.get("url", "")
                if title and url and urlparse(url).hostname == ALLOWED_ARTICLE_DOMAIN:
                    results.append((title, url))
            return results
        except (httpx.HTTPError, KeyError, ValueError):
            logger.debug("MS Learn search API error", exc_info=True)
            return []

    async def _fetch_article(self, url: str) -> str:
        """Fetch and extract text content from a Microsoft Learn article."""
        # Validate URL domain to prevent SSRF via malicious search results
        parsed = urlparse(url)
        if parsed.hostname != ALLOWED_ARTICLE_DOMAIN:
            logger.debug("Skipping non-Learn URL: %s", url)
            return ""

        try:
            resp = await self._client.get(
                url,
                headers={"Accept": "text/html"},
            )
            resp.raise_for_status()

            # Enforce size limit
            if len(resp.content) > MAX_RESPONSE_BYTES:
                logger.debug("Article too large: %s (%d bytes)", url, len(resp.content))
                return ""

            return await asyncio.to_thread(self._extract_text, resp.text)
        except (httpx.HTTPError, ValueError):
            logger.debug("Failed to fetch article: %s", url, exc_info=True)
            return ""

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML, stripping boilerplate."""
        text, _ = extract_html_text(html)
        return text
