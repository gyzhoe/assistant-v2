from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.main import app

# ---------------------------------------------------------------------------
# Integration tests for GET /models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_models_returns_default_model(client: AsyncClient) -> None:
    """GET /models should return the configured default model when LLM server is healthy."""
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
    assert len(data["models"]) == 1


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
