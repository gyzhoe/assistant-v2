import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.microsoft_docs import (
    CACHE_TTL_SECONDS,
    MAX_CACHE_ENTRIES,
    MicrosoftDocsService,
    WebContextDoc,
    _cache,
    _cache_key,
)

SAMPLE_SEARCH_JSON = {
    "results": [
        {"title": "Configure 802.1X", "url": "https://learn.microsoft.com/en-us/802x"},
        {"title": "Network Policy Server", "url": "https://learn.microsoft.com/en-us/nps"},
    ]
}

SAMPLE_HTML = """
<html>
<head><style>.hidden{display:none}</style></head>
<body>
<nav>Site nav</nav>
<main>
<h1>Configure 802.1X</h1>
<p>Step 1: Open Group Policy Editor.</p>
<p>Step 2: Navigate to network settings.</p>
</main>
<footer>Copyright 2024</footer>
<script>console.log('track')</script>
</body>
</html>
"""


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear the module-level cache before each test."""
    _cache.clear()


@pytest.mark.asyncio
async def test_search_returns_docs() -> None:
    """Mock httpx to return search results + article HTML, verify WebContextDoc list."""
    mock_search_resp = MagicMock()
    mock_search_resp.json.return_value = SAMPLE_SEARCH_JSON
    mock_search_resp.raise_for_status = MagicMock()

    mock_article_resp = MagicMock()
    mock_article_resp.text = SAMPLE_HTML
    mock_article_resp.content = SAMPLE_HTML.encode()
    mock_article_resp.raise_for_status = MagicMock()

    def fake_client_get(url: str, **kwargs: object) -> MagicMock:
        if "api/search" in url:
            return mock_search_resp
        return mock_article_resp

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = fake_client_get

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        docs = await svc.search("802.1X authentication")

    assert len(docs) == 2
    assert all(isinstance(d, WebContextDoc) for d in docs)
    assert docs[0].title == "Configure 802.1X"
    assert "Step 1" in docs[0].content
    # Boilerplate should be stripped
    assert "Site nav" not in docs[0].content
    assert "Copyright" not in docs[0].content
    assert "console.log" not in docs[0].content


@pytest.mark.asyncio
async def test_search_empty_keywords_returns_empty() -> None:
    svc = MicrosoftDocsService()
    result = await svc.search("")
    assert result == []
    result2 = await svc.search("   ")
    assert result2 == []


@pytest.mark.asyncio
async def test_search_api_timeout_returns_empty() -> None:
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.TimeoutException("timeout")

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        result = await svc.search("VPN troubleshooting")

    assert result == []


@pytest.mark.asyncio
async def test_search_api_error_returns_empty() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.request = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Server Error", request=mock_resp.request, response=mock_resp
    )

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        result = await svc.search("Active Directory")

    assert result == []


def test_extract_text_strips_boilerplate() -> None:
    svc = MicrosoftDocsService()
    text = svc._extract_text(SAMPLE_HTML)
    assert "Step 1" in text
    assert "Site nav" not in text
    assert "Copyright" not in text
    assert "console.log" not in text
    assert ".hidden" not in text


@pytest.mark.asyncio
async def test_cache_hit() -> None:
    """Second call with same keywords returns cached results without API call."""
    call_count = 0

    mock_search_resp = MagicMock()
    mock_search_resp.json.return_value = {
        "results": [{"title": "T1", "url": "https://learn.microsoft.com/en-us/test"}],
    }
    mock_search_resp.raise_for_status = MagicMock()

    mock_article_resp = MagicMock()
    mock_article_resp.text = "<html><body><main>Content here</main></body></html>"
    mock_article_resp.content = b"<html><body><main>Content here</main></body></html>"
    mock_article_resp.raise_for_status = MagicMock()

    def fake_get(url: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if "api/search" in url:
            return mock_search_resp
        return mock_article_resp

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get = fake_get

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        first = await svc.search("test query")
        calls_after_first = call_count
        second = await svc.search("test query")

    assert first == second
    assert call_count == calls_after_first  # No new HTTP calls on cache hit


@pytest.mark.asyncio
async def test_cache_expired() -> None:
    """Expired entries should be evicted."""
    key = _cache_key("expired query")
    _cache[key] = (time.monotonic() - CACHE_TTL_SECONDS - 1, [
        WebContextDoc(title="Old", url="https://old.com", content="old content"),
    ])

    mock_search_resp = MagicMock()
    mock_search_resp.json.return_value = {"results": []}
    mock_search_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_search_resp

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        result = await svc.search("expired query")

    # Cache was expired, new search returned empty
    assert result == []


@pytest.mark.asyncio
async def test_config_disabled_returns_empty() -> None:
    with patch("app.services.microsoft_docs.settings") as mock_settings:
        mock_settings.microsoft_docs_enabled = False
        svc = MicrosoftDocsService()
        result = await svc.search("802.1X setup")

    assert result == []


def test_fetch_article_rejects_non_learn_domain() -> None:
    """URLs not on learn.microsoft.com should be skipped (SSRF prevention)."""
    svc = MicrosoftDocsService()
    result = svc._fetch_article("https://evil.com/malicious")
    assert result == ""


def test_search_api_filters_non_learn_urls() -> None:
    """Search results with URLs outside learn.microsoft.com should be dropped."""
    mixed_results = {
        "results": [
            {"title": "Legit", "url": "https://learn.microsoft.com/en-us/legit"},
            {"title": "Evil", "url": "https://evil.com/phish"},
            {"title": "Also Legit", "url": "https://learn.microsoft.com/en-us/also"},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mixed_results
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("app.services.microsoft_docs.httpx.Client", return_value=mock_client):
        svc = MicrosoftDocsService()
        results = svc._search_api("test")

    assert len(results) == 2
    assert all(url.startswith("https://learn.microsoft.com") for _, url in results)


def test_cache_evicts_oldest_when_full() -> None:
    """Cache should evict the oldest entry when MAX_CACHE_ENTRIES is reached."""
    now = time.monotonic()
    # Fill cache to capacity
    for i in range(MAX_CACHE_ENTRIES):
        _cache[f"key_{i}"] = (now + i, [])

    assert len(_cache) == MAX_CACHE_ENTRIES

    # Adding one more should evict key_0 (oldest timestamp)
    from app.services.microsoft_docs import _set_cached
    _set_cached("overflow_query", [WebContextDoc(title="T", url="u", content="c")])

    assert len(_cache) == MAX_CACHE_ENTRIES
    assert "key_0" not in _cache
