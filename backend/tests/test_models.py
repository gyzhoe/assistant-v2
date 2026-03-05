from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers.models import _is_generate_model

# ---------------------------------------------------------------------------
# Unit tests for _is_generate_model helper
# ---------------------------------------------------------------------------


class TestIsGenerateModel:
    """Filter logic for excluding embedding-only models."""

    def test_generate_model_allowed(self) -> None:
        model = {"name": "qwen3.5:9b", "details": {"family": "qwen2"}}
        assert _is_generate_model(model) is True

    def test_nomic_bert_excluded(self) -> None:
        model = {"name": "nomic-embed-text", "details": {"family": "nomic-bert"}}
        assert _is_generate_model(model) is False

    def test_bert_family_excluded(self) -> None:
        model = {"name": "some-bert-model", "details": {"family": "bert"}}
        assert _is_generate_model(model) is False

    def test_case_insensitive(self) -> None:
        model = {"name": "nomic-embed-text", "details": {"family": "Nomic-Bert"}}
        assert _is_generate_model(model) is False

    def test_missing_details_allowed(self) -> None:
        """Models without details metadata should not be filtered out."""
        model = {"name": "mystery-model"}
        assert _is_generate_model(model) is True

    def test_empty_family_allowed(self) -> None:
        model = {"name": "mystery-model", "details": {"family": ""}}
        assert _is_generate_model(model) is True


# ---------------------------------------------------------------------------
# Integration tests for GET /models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_models_returns_list_excluding_embeddings(client: AsyncClient) -> None:
    """GET /models should return generate models and exclude embedding models."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "llama3.2:3b", "details": {"family": "llama"}},
            {"name": "nomic-embed-text", "details": {"family": "nomic-bert"}},
            {"name": "qwen3.5:9b", "details": {"family": "qwen2"}},
        ]
    }

    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(return_value=mock_resp)
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "llama3.2:3b" in data["models"]
    assert "qwen3.5:9b" in data["models"]
    assert "nomic-embed-text" not in data["models"]


@pytest.mark.asyncio
async def test_models_ollama_down_returns_503(client: AsyncClient) -> None:
    """GET /models should return 503 with OLLAMA_DOWN when Ollama is unreachable."""
    import httpx as httpx_mod

    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(side_effect=httpx_mod.ConnectError("Connection refused"))
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["error_code"] == "OLLAMA_DOWN"


@pytest.mark.asyncio
async def test_models_http_error_returns_502(client: AsyncClient) -> None:
    """GET /models should return 502 with MODEL_ERROR when Ollama returns an HTTP error."""
    import httpx as httpx_mod

    request = httpx_mod.Request("GET", "http://localhost:11435/api/tags")
    response = httpx_mod.Response(500, request=request)
    http_err = httpx_mod.HTTPStatusError("Server error", request=request, response=response)

    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(side_effect=http_err)
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 502
    data = resp.json()
    assert data["detail"]["error_code"] == "MODEL_ERROR"
    assert "500" in data["detail"]["message"]


@pytest.mark.asyncio
async def test_models_timeout_returns_503(client: AsyncClient) -> None:
    """GET /models should return 503 with OLLAMA_DOWN on timeout."""
    import httpx as httpx_mod

    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(side_effect=httpx_mod.ReadTimeout("timed out"))
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"]["error_code"] == "OLLAMA_DOWN"
