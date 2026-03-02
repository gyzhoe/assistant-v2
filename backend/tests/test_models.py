from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_models_returns_list(client: AsyncClient) -> None:
    """GET /models should return model names from Ollama."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "llama3.2:3b"},
            {"name": "nomic-embed-text"},
        ]
    }

    # Patch the shared Ollama client stored on app.state.llm_service._client
    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(return_value=mock_resp)
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "llama3.2:3b" in data["models"]
    assert "nomic-embed-text" in data["models"]


@pytest.mark.asyncio
async def test_models_ollama_down_returns_503(client: AsyncClient) -> None:
    """GET /models should return 503 when Ollama is unreachable."""
    import httpx as httpx_mod

    mock_ollama_client = MagicMock()
    mock_ollama_client.get = AsyncMock(side_effect=httpx_mod.ConnectError("Connection refused"))
    app.state.llm_service._client = mock_ollama_client

    resp = await client.get("/models")
    assert resp.status_code == 503
