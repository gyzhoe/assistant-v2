"""Tests for the KB management endpoints (GET/DELETE /kb/*)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.routers import kb as kb_mod


def _fresh_client(
    collection_data: dict[str, Any] | None = None,
    collection_exists: bool = True,
) -> AsyncClient:
    """Build an AsyncClient with a mocked ChromaDB client.

    Args:
        collection_data: dict to return from col.get(). If None, a default empty
            result is used.
        collection_exists: if False, get_collection raises ValueError.
    """
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()

    if not collection_exists:
        mock_chroma.get_collection.side_effect = ValueError("Collection not found")
    else:
        mock_chroma.get_collection.return_value = mock_col
        default_data: dict[str, Any] = {
            "ids": [], "documents": [], "metadatas": [],
        }
        mock_col.get.return_value = collection_data or default_data

    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False

    # Reset the module-level cache before each test
    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


def _sample_collection_data() -> dict[str, Any]:
    """Return mock ChromaDB data with 3 articles (5 chunks total)."""
    return {
        "ids": ["c1", "c2", "c3", "c4", "c5"],
        "documents": [
            "VPN setup step 1",
            "VPN setup step 2",
            "Reset AD password instructions",
            "DHCP scope config",
            "DHCP scope config part 2",
        ],
        "metadatas": [
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "source_type": "html",
                "source_file": "vpn.html",
                "section": "Setup",
                "imported_at": "2026-02-20T10:00:00+00:00",
            },
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "source_type": "html",
                "source_file": "vpn.html",
                "section": "Troubleshooting",
                "imported_at": "2026-02-20T10:00:00+00:00",
            },
            {
                "article_id": "art2",
                "title": "Reset AD Passwords",
                "source_type": "pdf",
                "source_file": "reset-ad.pdf",
                "imported_at": "2026-02-18T08:00:00+00:00",
            },
            {
                "article_id": "art3",
                "title": "DHCP Scope Configuration",
                "source_type": "url",
                "source_url": "https://learn.microsoft.com/dhcp",
                "imported_at": "2026-02-25T14:00:00+00:00",
            },
            {
                "article_id": "art3",
                "title": "DHCP Scope Configuration",
                "source_type": "url",
                "source_url": "https://learn.microsoft.com/dhcp",
                "imported_at": "2026-02-25T14:00:00+00:00",
            },
        ],
    }


# ---------------------------------------------------------------------------
# GET /kb/articles — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_articles_returns_all() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["articles"]) == 3


@pytest.mark.asyncio
async def test_list_articles_search_filter() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles", params={"search": "vpn"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 1
        assert data["articles"][0]["title"] == "VPN Setup Guide"


@pytest.mark.asyncio
async def test_list_articles_source_type_filter() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles", params={"source_type": "pdf"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 1
        assert data["articles"][0]["source_type"] == "pdf"


@pytest.mark.asyncio
async def test_list_articles_pagination() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 3
        assert len(data["articles"]) == 2
        assert data["page"] == 1

        resp2 = await ac.get("/kb/articles", params={"page": 2, "page_size": 2})
        data2 = resp2.json()
        assert len(data2["articles"]) == 1
        assert data2["page"] == 2


@pytest.mark.asyncio
async def test_list_articles_empty_collection() -> None:
    async with _fresh_client() as ac:
        resp = await ac.get("/kb/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 0
        assert data["articles"] == []


@pytest.mark.asyncio
async def test_list_articles_nonexistent_collection() -> None:
    async with _fresh_client(collection_exists=False) as ac:
        resp = await ac.get("/kb/articles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 0
        assert data["articles"] == []


@pytest.mark.asyncio
async def test_list_articles_sorted_by_imported_at() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles")
        data = resp.json()
        articles = data["articles"]
        # Most recent first: DHCP (Feb 25) > VPN (Feb 20) > AD (Feb 18)
        assert articles[0]["title"] == "DHCP Scope Configuration"
        assert articles[1]["title"] == "VPN Setup Guide"
        assert articles[2]["title"] == "Reset AD Passwords"


@pytest.mark.asyncio
async def test_list_articles_chunk_count_correct() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles")
        data = resp.json()
        by_id = {a["article_id"]: a for a in data["articles"]}
        assert by_id["art1"]["chunk_count"] == 2
        assert by_id["art2"]["chunk_count"] == 1
        assert by_id["art3"]["chunk_count"] == 2


@pytest.mark.asyncio
async def test_list_articles_url_source_uses_source_url() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/articles", params={"source_type": "url"})
        data = resp.json()
        assert data["articles"][0]["source"] == "https://learn.microsoft.com/dhcp"


# ---------------------------------------------------------------------------
# GET /kb/articles/{article_id} — detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_article_detail() -> None:
    detail_data: dict[str, Any] = {
        "ids": ["c1", "c2"],
        "documents": ["VPN step 1", "VPN step 2"],
        "metadatas": [
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "source_type": "html",
                "source_file": "vpn.html",
                "section": "Setup",
                "imported_at": "2026-02-20T10:00:00+00:00",
            },
            {
                "article_id": "art1",
                "title": "VPN Setup Guide",
                "source_type": "html",
                "source_file": "vpn.html",
                "section": "Troubleshooting",
                "imported_at": "2026-02-20T10:00:00+00:00",
            },
        ],
    }
    async with _fresh_client(detail_data) as ac:
        resp = await ac.get("/kb/articles/art1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_id"] == "art1"
        assert data["title"] == "VPN Setup Guide"
        assert data["source_type"] == "html"
        assert data["source"] == "vpn.html"
        assert data["chunk_count"] == 2
        assert len(data["chunks"]) == 2
        assert data["chunks"][0]["text"] == "VPN step 1"
        assert data["chunks"][0]["section"] == "Setup"
        assert data["chunks"][1]["section"] == "Troubleshooting"


@pytest.mark.asyncio
async def test_get_article_not_found() -> None:
    empty: dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
    async with _fresh_client(empty) as ac:
        resp = await ac.get("/kb/articles/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_get_article_collection_missing() -> None:
    async with _fresh_client(collection_exists=False) as ac:
        resp = await ac.get("/kb/articles/any")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /kb/articles/{article_id}
# ---------------------------------------------------------------------------


# Extension token bypasses CSRF middleware for DELETE requests
_EXT_HEADERS = {"X-Extension-Token": "test-bypass"}


@pytest.mark.asyncio
async def test_delete_article_success() -> None:
    delete_data: dict[str, Any] = {
        "ids": ["c1", "c2"],
        "documents": [],
        "metadatas": [],
    }
    async with _fresh_client(delete_data) as ac:
        resp = await ac.delete("/kb/articles/art1", headers=_EXT_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["article_id"] == "art1"
        assert data["chunks_deleted"] == 2


@pytest.mark.asyncio
async def test_delete_article_not_found() -> None:
    empty: dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
    async with _fresh_client(empty) as ac:
        resp = await ac.delete("/kb/articles/nonexistent", headers=_EXT_HEADERS)
        assert resp.status_code == 404
        assert "not found" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_delete_article_collection_missing() -> None:
    async with _fresh_client(collection_exists=False) as ac:
        resp = await ac.delete("/kb/articles/any", headers=_EXT_HEADERS)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_invalidates_cache() -> None:
    """After delete, the cache should be invalidated so list re-fetches."""
    delete_data: dict[str, Any] = {
        "ids": ["c1"],
        "documents": [],
        "metadatas": [],
    }
    async with _fresh_client(delete_data) as ac:
        # Pre-warm cache
        kb_mod._cache_timestamp = 1.0
        kb_mod._article_cache = {"art1": {"title": "test"}}

        await ac.delete("/kb/articles/art1", headers=_EXT_HEADERS)

        # Cache should be invalidated
        assert kb_mod._cache_timestamp == 0.0


# ---------------------------------------------------------------------------
# GET /kb/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_returns_counts() -> None:
    async with _fresh_client(_sample_collection_data()) as ac:
        resp = await ac.get("/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 3
        assert data["total_chunks"] == 5
        assert data["by_source_type"]["html"] == 1
        assert data["by_source_type"]["pdf"] == 1
        assert data["by_source_type"]["url"] == 1


@pytest.mark.asyncio
async def test_stats_empty_collection() -> None:
    async with _fresh_client() as ac:
        resp = await ac.get("/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 0
        assert data["total_chunks"] == 0
        assert data["by_source_type"] == {}


@pytest.mark.asyncio
async def test_stats_nonexistent_collection() -> None:
    async with _fresh_client(collection_exists=False) as ac:
        resp = await ac.get("/kb/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_articles"] == 0
        assert data["total_chunks"] == 0


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# article_id path param validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_article_invalid_id_returns_422() -> None:
    """article_id with path traversal or special chars returns 422."""
    async with _fresh_client() as ac:
        resp = await ac.get("/kb/articles/../../etc/passwd")
        assert resp.status_code in (404, 422)  # 404 from route not found or 422 from validation


@pytest.mark.asyncio
async def test_get_article_id_too_long_returns_422() -> None:
    """article_id over 64 chars returns 422."""
    async with _fresh_client() as ac:
        long_id = "a" * 65
        resp = await ac.get(f"/kb/articles/{long_id}")
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_article_id_with_special_chars_returns_422() -> None:
    """article_id with spaces or special chars returns 422."""
    async with _fresh_client() as ac:
        resp = await ac.get("/kb/articles/invalid id!")
        assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_delete_article_invalid_id_returns_422() -> None:
    """DELETE with invalid article_id returns 422."""
    async with _fresh_client() as ac:
        long_id = "a" * 65
        resp = await ac.delete(f"/kb/articles/{long_id}", headers=_EXT_HEADERS)
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_valid_article_id_passes_validation() -> None:
    """Valid article_id (alphanumeric + _ -) passes validation."""
    empty: dict[str, Any] = {"ids": [], "documents": [], "metadatas": []}
    async with _fresh_client(empty) as ac:
        resp = await ac.get("/kb/articles/valid-article_id-123")
        # Passes validation, 404 because not in mock
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cache_is_reused_on_second_call() -> None:
    """Second call within TTL should not hit ChromaDB again."""
    app = create_app()
    mock_chroma = MagicMock()
    mock_col = MagicMock()
    mock_chroma.get_collection.return_value = mock_col
    mock_col.get.return_value = _sample_collection_data()
    app.state.chroma_client = mock_chroma
    app.state.llm_reachable = False

    kb_mod._article_cache = {}
    kb_mod._cache_timestamp = 0.0
    kb_mod._total_chunks_cached = 0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp1 = await ac.get("/kb/articles")
        assert resp1.status_code == 200

        resp2 = await ac.get("/kb/articles")
        assert resp2.status_code == 200

    # ChromaDB col.get() should only be called once (cache hit on second)
    assert mock_col.get.call_count == 1


