"""Tests for the /ingest/url endpoint.

Each test uses a fresh app (via create_app()) so module-level semaphore and
middleware state are isolated.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


def _fresh_client(app: object | None = None) -> AsyncClient:
    """Build an AsyncClient around a fresh app with mocked state."""
    if app is None:
        fresh_app = create_app()
    else:
        fresh_app = app  # type: ignore[assignment]
    fresh_app.state.chroma_client = MagicMock()  # type: ignore[union-attr]
    fresh_app.state.ollama_reachable = False  # type: ignore[union-attr]
    return AsyncClient(
        transport=ASGITransport(app=fresh_app),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_success() -> None:
    mock_chunks = [
        ("id1", "chunk1", {"article_id": "a1", "title": "Example Page", "source_url": "https://example.com", "source_type": "url"}),
        ("id2", "chunk2", {"article_id": "a1", "title": "Example Page", "source_url": "https://example.com", "source_type": "url"}),
    ]

    fresh_app = create_app()
    fresh_app.state.chroma_client = MagicMock()
    fresh_app.state.ollama_reachable = False
    fresh_app.state.chroma_client.get_or_create_collection.return_value = MagicMock()

    async with _fresh_client(fresh_app) as ac:
        with (
            patch("app.routers.ingest.load_url", return_value=iter(mock_chunks)),
            patch("app.routers.ingest.EmbedService"),
            patch("app.routers.ingest.IngestionPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.upsert_stream.return_value = 2
            mock_pipeline_cls.return_value = mock_pipeline

            resp = await ac.post(
                "/ingest/url",
                json={"url": "https://example.com/article"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["collection"] == "kb_articles"
    assert data["chunks_ingested"] == 2
    assert data["title"] == "Example Page"
    assert data["warning"] is None


# ---------------------------------------------------------------------------
# SSRF → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_ssrf_returns_422() -> None:
    from ingestion.url_loader import SSRFError

    async with _fresh_client() as ac:
        with patch("app.routers.ingest.load_url", side_effect=SSRFError("private IP")):
            resp = await ac.post(
                "/ingest/url",
                json={"url": "http://localhost:8080/admin"},
            )

    assert resp.status_code == 422
    assert "private IP" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Invalid content type → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_invalid_content_type_returns_422() -> None:
    from ingestion.url_loader import ContentTypeError

    async with _fresh_client() as ac:
        with patch("app.routers.ingest.load_url", side_effect=ContentTypeError("image/png not supported")):
            resp = await ac.post(
                "/ingest/url",
                json={"url": "https://example.com/image.png"},
            )

    assert resp.status_code == 422
    assert "image/png" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Too large → 413
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_too_large_returns_413() -> None:
    from ingestion.url_loader import ResponseTooLargeError

    async with _fresh_client() as ac:
        with patch("app.routers.ingest.load_url", side_effect=ResponseTooLargeError("too big")):
            resp = await ac.post(
                "/ingest/url",
                json={"url": "https://example.com/huge-page"},
            )

    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert "PAYLOAD_TOO_LARGE" in detail.get("error_code", "")


# ---------------------------------------------------------------------------
# Ollama down → 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_ollama_down_returns_503() -> None:
    mock_chunks = [("id1", "chunk1", {"title": "T", "source_url": "u", "article_id": "a", "source_type": "url"})]

    fresh_app = create_app()
    fresh_app.state.chroma_client = MagicMock()
    fresh_app.state.ollama_reachable = False
    fresh_app.state.chroma_client.get_or_create_collection.return_value = MagicMock()

    async with _fresh_client(fresh_app) as ac:
        with (
            patch("app.routers.ingest.load_url", return_value=iter(mock_chunks)),
            patch("app.routers.ingest.EmbedService"),
            patch("app.routers.ingest.IngestionPipeline") as mock_pipeline_cls,
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.upsert_stream.side_effect = ConnectionError("Ollama down")
            mock_pipeline_cls.return_value = mock_pipeline

            resp = await ac.post(
                "/ingest/url",
                json={"url": "https://example.com"},
            )

    assert resp.status_code == 503
    assert "Ollama" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# No content → warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_no_content_returns_warning() -> None:
    async with _fresh_client() as ac:
        with patch("app.routers.ingest.load_url", return_value=iter([])):
            resp = await ac.post(
                "/ingest/url",
                json={"url": "https://example.com/empty"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["chunks_ingested"] == 0
    assert data["warning"] is not None
    assert "No text content" in data["warning"]


# ---------------------------------------------------------------------------
# Concurrent → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_concurrent_returns_409() -> None:
    fresh_app = create_app()
    fresh_app.state.chroma_client = MagicMock()
    fresh_app.state.ollama_reachable = False

    import app.routers.ingest as ingest_mod

    ingest_mod._upload_semaphore = asyncio.Semaphore(1)

    slow_event = asyncio.Event()

    def slow_load_url(url: str):
        for _ in range(50):
            if slow_event.is_set():
                break
            time.sleep(0.1)
        return [("id1", "chunk", {"title": "T", "source_url": url, "article_id": "a", "source_type": "url"})]

    with (
        patch("app.routers.ingest.load_url", side_effect=slow_load_url),
        patch("app.routers.ingest.EmbedService"),
        patch("app.routers.ingest.IngestionPipeline") as mock_pipeline_cls,
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.upsert_stream.return_value = 1
        mock_pipeline_cls.return_value = mock_pipeline
        fresh_app.state.chroma_client.get_or_create_collection.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
        ) as ac:
            task1 = asyncio.create_task(
                ac.post("/ingest/url", json={"url": "https://example.com/a"})
            )
            await asyncio.sleep(0.2)

            task2 = asyncio.create_task(
                ac.post("/ingest/url", json={"url": "https://example.com/b"})
            )

            resp2 = await task2
            slow_event.set()
            resp1 = await task1

    status_codes = sorted([resp1.status_code, resp2.status_code])
    assert 200 in status_codes, "One request should succeed"
    assert 409 in status_codes, "The other should get 409"


# ---------------------------------------------------------------------------
# Invalid URL → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_url_invalid_url_returns_422() -> None:
    async with _fresh_client() as ac:
        resp = await ac.post(
            "/ingest/url",
            json={"url": "not-a-valid-url"},
        )

    assert resp.status_code == 422
