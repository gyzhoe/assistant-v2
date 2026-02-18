import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_generate_missing_subject_returns_422(client: AsyncClient) -> None:
    response = await client.post("/generate", json={
        "ticket_description": "Cannot login to VPN"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_missing_description_returns_422(client: AsyncClient) -> None:
    response = await client.post("/generate", json={
        "ticket_subject": "VPN Issue"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_returns_reply(client: AsyncClient) -> None:
    with (
        patch("app.routers.generate.RAGService") as MockRAG,
        patch("app.routers.generate.LLMService") as MockLLM,
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        MockRAG.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Hi Alex, here is the fix...")
        MockLLM.return_value = mock_llm

        response = await client.post("/generate", json={
            "ticket_subject": "Cannot access network drive",
            "ticket_description": "Network drive not accessible after password reset",
            "requester_name": "Alex Johnson",
            "category": "Network",
            "status": "Open",
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert data["reply"] == "Hi Alex, here is the fix..."
        assert "model_used" in data
        assert "context_docs" in data
        assert "latency_ms" in data


@pytest.mark.asyncio
async def test_generate_ollama_down_returns_503(client: AsyncClient) -> None:
    with (
        patch("app.routers.generate.RAGService") as MockRAG,
        patch("app.routers.generate.LLMService") as MockLLM,
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        MockRAG.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            side_effect=ConnectionError("Ollama service unreachable at http://localhost:11434")
        )
        MockLLM.return_value = mock_llm

        response = await client.post("/generate", json={
            "ticket_subject": "Test",
            "ticket_description": "Test description",
        })
        assert response.status_code == 503
