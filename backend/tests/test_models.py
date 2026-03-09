"""Tests for /models endpoint, model name mapping, scan_models, and download endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.constants import MODEL_DISPLAY_NAMES, MODEL_GGUF_FILES
from app.main import create_app
from app.routers.models import _gguf_display_name, scan_models
from app.services.model_download_service import ModelDownloadService
from tests.helpers import setup_app_state

# ── Model name mapping ────────────────────────────────────────────


def test_display_name_known_model() -> None:
    assert _gguf_display_name("Qwen3.5-9B-Q4_K_M.gguf") == "qwen3.5:9b"
    assert _gguf_display_name("Qwen3-14B-Q4_K_M.gguf") == "qwen3:14b"


def test_display_name_unknown_model() -> None:
    assert _gguf_display_name("SomeModel-7B.gguf") == "somemodel-7b"


def test_gguf_reverse_mapping() -> None:
    assert MODEL_GGUF_FILES["qwen3.5:9b"] == "Qwen3.5-9B-Q4_K_M.gguf"
    assert MODEL_GGUF_FILES["qwen3:14b"] == "Qwen3-14B-Q4_K_M.gguf"


def test_display_names_and_gguf_files_are_inverse() -> None:
    for gguf, display in MODEL_DISPLAY_NAMES.items():
        assert MODEL_GGUF_FILES[display] == gguf


# ── scan_models ───────────────────────────────────────────────────


def test_scan_models_empty_dir(tmp_path: Path) -> None:
    with patch("app.routers.models._MODELS_DIR", tmp_path):
        assert scan_models() == []


def test_scan_models_excludes_embed(tmp_path: Path) -> None:
    (tmp_path / "Qwen3.5-9B-Q4_K_M.gguf").touch()
    (tmp_path / "nomic-embed-text-v1.5.f16.gguf").touch()
    with patch("app.routers.models._MODELS_DIR", tmp_path):
        result = scan_models()
    assert result == ["qwen3.5:9b"]


def test_scan_models_nonexistent_dir() -> None:
    with patch("app.routers.models._MODELS_DIR", Path("/nonexistent/path")):
        assert scan_models() == []


def test_scan_models_multiple(tmp_path: Path) -> None:
    (tmp_path / "Qwen3.5-9B-Q4_K_M.gguf").touch()
    (tmp_path / "Qwen3-14B-Q4_K_M.gguf").touch()
    with patch("app.routers.models._MODELS_DIR", tmp_path):
        result = scan_models()
    assert "qwen3.5:9b" in result
    assert "qwen3:14b" in result


# ── GET /models endpoint ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_models_returns_list_and_current(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """GET /models returns available models and current model."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(return_value=mock_resp)
    test_app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "current" in data
    assert isinstance(data["models"], list)
    assert data["current"] == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_models_falls_back_to_default_when_no_dir(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """GET /models falls back to [default_model] when models dir is empty."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(return_value=mock_resp)
    test_app.state.llm_service._client = mock_llm_client

    with patch("app.routers.models._MODELS_DIR", Path("/nonexistent")):
        resp = await client.get("/models")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) >= 1


@pytest.mark.asyncio
async def test_models_llm_down_returns_503(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """GET /models should return 503 with LLM_DOWN when LLM server is unreachable."""
    import httpx as httpx_mod

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=httpx_mod.ConnectError("Connection refused"))
    test_app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error_code"] == "LLM_DOWN"


@pytest.mark.asyncio
async def test_models_http_error_returns_502(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """GET /models should return 502 with MODEL_ERROR when LLM server returns an HTTP error."""
    import httpx as httpx_mod

    request = httpx_mod.Request("GET", "http://localhost:11435/health")
    response = httpx_mod.Response(500, request=request)
    http_err = httpx_mod.HTTPStatusError("Server error", request=request, response=response)

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=http_err)
    test_app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 502
    data = resp.json()
    assert data["error_code"] == "MODEL_ERROR"
    assert "500" in data["message"]


@pytest.mark.asyncio
async def test_models_timeout_returns_503(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """GET /models should return 503 with LLM_DOWN on timeout."""
    import httpx as httpx_mod

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=httpx_mod.ReadTimeout("timed out"))
    test_app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error_code"] == "LLM_DOWN"


# ── GET /models includes model_info ──────────────────────────────


def _make_download_app() -> object:
    test_app = create_app()
    setup_app_state(test_app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    test_app.state.llm_service._client.get = AsyncMock(return_value=mock_resp)
    return test_app


def _make_download_client(test_app: object | None = None) -> AsyncClient:
    if test_app is None:
        test_app = _make_download_app()
    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_models_includes_model_info() -> None:
    test_app = _make_download_app()
    async with _make_download_client(test_app) as ac:
        response = await ac.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert "model_info" in data
    info = data["model_info"]
    assert "qwen3.5:9b" in info
    assert "qwen3:14b" in info
    for entry in info.values():
        assert "downloaded" in entry
        assert "size_bytes" in entry
        assert "description" in entry
        assert "gguf_name" in entry


# ── POST /models/download ───────────────────────────────────────


@pytest.mark.asyncio
async def test_download_starts_with_specific_models() -> None:
    test_app = _make_download_app()
    svc = test_app.state.model_download_service
    with patch.object(
        svc, "start_download",
        return_value={"status": "started", "models": ["Qwen3.5-9B-Q4_K_M.gguf"]},
    ):
        async with _make_download_client(test_app) as ac:
            response = await ac.post(
                "/models/download",
                json={"models": ["Qwen3.5-9B-Q4_K_M.gguf"]},
            )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert "Qwen3.5-9B-Q4_K_M.gguf" in data["models"]


@pytest.mark.asyncio
async def test_download_empty_list_downloads_all_missing() -> None:
    test_app = _make_download_app()
    svc = test_app.state.model_download_service
    with (
        patch("app.routers.models._MODELS_DIR", Path("/fake/nonexistent")),
        patch.object(
            svc, "start_download",
            return_value={"status": "started", "models": ["Qwen3.5-9B-Q4_K_M.gguf", "Qwen3-14B-Q4_K_M.gguf"]},
        ),
    ):
        async with _make_download_client(test_app) as ac:
            response = await ac.post("/models/download", json={"models": []})
    assert response.status_code == 200
    assert response.json()["status"] == "started"


@pytest.mark.asyncio
async def test_download_when_already_downloading() -> None:
    test_app = _make_download_app()
    svc = test_app.state.model_download_service
    with patch.object(
        svc, "start_download",
        return_value={"status": "already_downloading"},
    ):
        async with _make_download_client(test_app) as ac:
            response = await ac.post(
                "/models/download",
                json={"models": ["Qwen3.5-9B-Q4_K_M.gguf"]},
            )
    assert response.status_code == 200
    assert response.json()["status"] == "already_downloading"


# ── GET /models/download/status ──────────────────────────────────


@pytest.mark.asyncio
async def test_download_status_returns_state() -> None:
    test_app = _make_download_app()
    async with _make_download_client(test_app) as ac:
        response = await ac.get("/models/download/status")
    assert response.status_code == 200
    data = response.json()
    assert "downloading" in data
    assert data["downloading"] is False
    assert "current_model" in data
    assert "bytes_downloaded" in data
    assert "bytes_total" in data
    assert "models_completed" in data
    assert "models_total" in data
    assert "error" in data


# ── POST /models/download/cancel ─────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_when_not_downloading() -> None:
    test_app = _make_download_app()
    async with _make_download_client(test_app) as ac:
        response = await ac.post("/models/download/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "not_downloading"


# ── ModelDownloadService unit tests ──────────────────────────────


def test_service_get_status_default() -> None:
    svc = ModelDownloadService()
    status = svc.get_status()
    assert status["downloading"] is False
    assert status["error"] == ""


def test_service_cancel_when_not_downloading() -> None:
    svc = ModelDownloadService()
    result = svc.cancel()
    assert result["status"] == "not_downloading"


def test_service_start_with_unknown_model() -> None:
    svc = ModelDownloadService()
    result = svc.start_download(["nonexistent.gguf"], Path("/tmp/models"))
    assert result["status"] == "error"
    assert "Unknown model" in str(result["error"])
