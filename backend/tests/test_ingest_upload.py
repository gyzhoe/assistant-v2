"""Tests for the /ingest/upload endpoint.

Each test uses a fresh app (via create_app()) so module-level semaphore and
middleware state are isolated.
"""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
from pathlib import Path
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


def _json_file_bytes(data: list[dict[str, str]]) -> bytes:
    return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_json_file_success() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch(
            "app.routers.ingest.EmbedService"
        ):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 5)
            mock_pipeline_cls.return_value = mock_pipeline

            content = _json_file_bytes([{"id": "1", "subject": "A", "description": "B"}])
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("tickets.json", io.BytesIO(content), "application/json")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["filename"] == "tickets.json"
            assert data["collection"] == "whd_tickets"
            assert data["chunks_ingested"] == 5
            assert "processing_time_ms" in data
            assert data["warning"] is None


@pytest.mark.asyncio
async def test_upload_csv_file_success() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 3)
            mock_pipeline_cls.return_value = mock_pipeline

            csv_content = b"id,subject,description\n1,Test,Desc\n"
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
            )
            assert resp.status_code == 200
            assert resp.json()["collection"] == "whd_tickets"


@pytest.mark.asyncio
async def test_upload_html_file_success() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("kb_articles", 2)
            mock_pipeline_cls.return_value = mock_pipeline

            html_content = b"<html><body><p>Hello</p></body></html>"
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("article.html", io.BytesIO(html_content), "text/html")},
            )
            assert resp.status_code == 200
            assert resp.json()["collection"] == "kb_articles"


@pytest.mark.asyncio
async def test_upload_pdf_file_success() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("kb_articles", 10)
            mock_pipeline_cls.return_value = mock_pipeline

            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            )
            assert resp.status_code == 200
            assert resp.json()["collection"] == "kb_articles"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_invalid_extension_returns_422() -> None:
    async with _fresh_client() as ac:
        resp = await ac.post(
            "/ingest/upload",
            files={"file": ("doc.docx", io.BytesIO(b"fake"), "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert "Unsupported file type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file_returns_422() -> None:
    async with _fresh_client() as ac:
        resp = await ac.post(
            "/ingest/upload",
            files={"file": ("empty.json", io.BytesIO(b""), "application/json")},
        )
        assert resp.status_code == 422
        assert "empty" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Oversized file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_oversized_file_returns_413() -> None:
    with patch("app.routers.ingest.settings") as mock_settings:
        mock_settings.max_upload_bytes = 100  # very small limit

        async with _fresh_client() as ac:
            big_content = b"x" * 200
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("big.json", io.BytesIO(big_content), "application/json")},
            )
            assert resp.status_code == 413
            detail = resp.json()["detail"]
            assert "PAYLOAD_TOO_LARGE" in detail.get("error_code", "")


# ---------------------------------------------------------------------------
# Path traversal sanitization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_path_traversal_sanitized() -> None:
    """Filenames with directory components should be sanitized to just the name."""
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 1)
            mock_pipeline_cls.return_value = mock_pipeline

            content = _json_file_bytes([{"id": "1", "subject": "A", "description": "B"}])
            resp = await ac.post(
                "/ingest/upload",
                files={
                    "file": (
                        "../../etc/passwd.json",
                        io.BytesIO(content),
                        "application/json",
                    )
                },
            )
            assert resp.status_code == 200
            assert resp.json()["filename"] == "passwd.json"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_ollama_down_returns_503() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.side_effect = ConnectionError("Ollama down")
            mock_pipeline_cls.return_value = mock_pipeline

            content = _json_file_bytes([{"id": "1", "subject": "A", "description": "B"}])
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("tickets.json", io.BytesIO(content), "application/json")},
            )
            assert resp.status_code == 503
            assert "Ollama" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_corrupt_file_returns_422() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.side_effect = ValueError("Bad JSON")
            mock_pipeline_cls.return_value = mock_pipeline

            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("bad.json", io.BytesIO(b"not json"), "application/json")},
            )
            assert resp.status_code == 422
            assert "Bad JSON" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Zero chunks → warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_zero_chunks_returns_warning() -> None:
    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("kb_articles", 0)
            mock_pipeline_cls.return_value = mock_pipeline

            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("empty.html", io.BytesIO(b"<html></html>"), "text/html")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["chunks_ingested"] == 0
            assert data["warning"] is not None
            assert "No text content" in data["warning"]


# ---------------------------------------------------------------------------
# Concurrent upload → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_upload_returns_409() -> None:
    """Two simultaneous uploads: one succeeds, the other gets 409."""
    fresh_app = create_app()
    fresh_app.state.chroma_client = MagicMock()
    fresh_app.state.ollama_reachable = False

    # Reset the module-level semaphore for this test
    import app.routers.ingest as ingest_mod

    ingest_mod._upload_semaphore = asyncio.Semaphore(1)

    slow_event = asyncio.Event()

    def slow_ingest_file(path: Path) -> tuple[str, int]:
        """Simulate a slow ingestion that blocks until event is set."""
        import time
        # Busy wait for up to 5s (running in thread, can't await)
        for _ in range(50):
            if slow_event.is_set():
                break
            time.sleep(0.1)
        return ("whd_tickets", 1)

    with patch(
        "app.routers.ingest.IngestionPipeline"
    ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
        mock_pipeline = MagicMock()
        mock_pipeline.ingest_file.side_effect = slow_ingest_file
        mock_pipeline_cls.return_value = mock_pipeline

        content = _json_file_bytes([{"id": "1", "subject": "A", "description": "B"}])

        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
        ) as ac:
            # Launch the slow upload
            task1 = asyncio.create_task(
                ac.post(
                    "/ingest/upload",
                    files={"file": ("a.json", io.BytesIO(content), "application/json")},
                )
            )
            # Give it a moment to acquire the semaphore
            await asyncio.sleep(0.2)

            # Second upload should be rejected
            task2 = asyncio.create_task(
                ac.post(
                    "/ingest/upload",
                    files={"file": ("b.json", io.BytesIO(content), "application/json")},
                )
            )

            resp2 = await task2
            # Release the slow upload
            slow_event.set()
            resp1 = await task1

        status_codes = sorted([resp1.status_code, resp2.status_code])
        assert 200 in status_codes, "One upload should succeed"
        assert 409 in status_codes, "The other should get 409"


# ---------------------------------------------------------------------------
# Temp file cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_temp_file_cleaned_up_after_upload() -> None:
    """After successful upload, no temp files should remain."""
    temp_files_before = set(Path(tempfile.gettempdir()).glob("ingest_*"))

    async with _fresh_client() as ac:
        with patch(
            "app.routers.ingest.IngestionPipeline"
        ) as mock_pipeline_cls, patch("app.routers.ingest.EmbedService"):
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 1)
            mock_pipeline_cls.return_value = mock_pipeline

            content = _json_file_bytes([{"id": "1", "subject": "A", "description": "B"}])
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("tickets.json", io.BytesIO(content), "application/json")},
            )
            assert resp.status_code == 200

    temp_files_after = set(Path(tempfile.gettempdir()).glob("ingest_*"))
    new_temp_files = temp_files_after - temp_files_before
    assert len(new_temp_files) == 0, f"Temp files not cleaned up: {new_temp_files}"
