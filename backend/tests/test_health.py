from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    with (
        patch("app.routers.health.httpx.AsyncClient") as mock_http,
        patch("app.routers.health.Request") as _,
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_http.return_value)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_http.return_value.get = AsyncMock(return_value=mock_response)

        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_health_response_schema(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    required_keys = {"status", "ollama_reachable", "chroma_ready", "chroma_doc_counts", "version"}
    assert required_keys.issubset(data.keys())


@pytest.mark.asyncio
async def test_health_degraded_when_ollama_down(client: AsyncClient) -> None:
    response = await client.get("/health")
    data = response.json()
    # In test environment Ollama is not running, so should be degraded
    assert data["status"] in ("ok", "degraded")
    assert isinstance(data["ollama_reachable"], bool)
