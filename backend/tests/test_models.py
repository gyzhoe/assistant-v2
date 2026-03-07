"""Tests for /models endpoint, model name mapping, and scan_models utility."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.constants import MODEL_DISPLAY_NAMES, MODEL_GGUF_FILES
from app.main import app
from app.routers.models import _gguf_display_name, scan_models

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
async def test_models_returns_list_and_current(client: AsyncClient) -> None:
    """GET /models returns available models and current model."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(return_value=mock_resp)
    app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "current" in data
    assert isinstance(data["models"], list)
    assert data["current"] == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_models_falls_back_to_default_when_no_dir(client: AsyncClient) -> None:
    """GET /models falls back to [default_model] when models dir is empty."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(return_value=mock_resp)
    app.state.llm_service._client = mock_llm_client

    with patch("app.routers.models._MODELS_DIR", Path("/nonexistent")):
        resp = await client.get("/models")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["models"]) >= 1


@pytest.mark.asyncio
async def test_models_llm_down_returns_503(client: AsyncClient) -> None:
    """GET /models should return 503 with LLM_DOWN when LLM server is unreachable."""
    import httpx as httpx_mod

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=httpx_mod.ConnectError("Connection refused"))
    app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["error_code"] == "LLM_DOWN"


@pytest.mark.asyncio
async def test_models_http_error_returns_502(client: AsyncClient) -> None:
    """GET /models should return 502 with MODEL_ERROR when LLM server returns an HTTP error."""
    import httpx as httpx_mod

    request = httpx_mod.Request("GET", "http://localhost:11435/health")
    response = httpx_mod.Response(500, request=request)
    http_err = httpx_mod.HTTPStatusError("Server error", request=request, response=response)

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=http_err)
    app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 502
    data = resp.json()
    assert data["detail"]["error_code"] == "MODEL_ERROR"
    assert "500" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_models_timeout_returns_503(client: AsyncClient) -> None:
    """GET /models should return 503 with LLM_DOWN on timeout."""
    import httpx as httpx_mod

    mock_llm_client = MagicMock()
    mock_llm_client.get = AsyncMock(side_effect=httpx_mod.ReadTimeout("timed out"))
    app.state.llm_service._client = mock_llm_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["error_code"] == "LLM_DOWN"
