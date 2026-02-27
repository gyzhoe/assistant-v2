from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.services.microsoft_docs import WebContextDoc


def _mock_ms_docs(return_value: list[WebContextDoc] | None = None) -> MagicMock:
    """Create a mock MicrosoftDocsService class."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.search = AsyncMock(return_value=return_value or [])
    mock_cls.return_value = mock_instance
    return mock_cls


@pytest.mark.asyncio
async def test_generate_without_subject_returns_200(client: AsyncClient) -> None:
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService", _mock_ms_docs()),
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="VPN fix applied.")
        mock_llm_cls.return_value = mock_llm

        response = await client.post("/generate", json={
            "ticket_description": "Cannot login to VPN",
        })
        assert response.status_code == 200
        assert response.json()["reply"] == "VPN fix applied."


@pytest.mark.asyncio
async def test_generate_without_description_returns_200(client: AsyncClient) -> None:
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService", _mock_ms_docs()),
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="VPN issue resolved.")
        mock_llm_cls.return_value = mock_llm

        response = await client.post("/generate", json={
            "ticket_subject": "VPN Issue",
        })
        assert response.status_code == 200
        assert response.json()["reply"] == "VPN issue resolved."


@pytest.mark.asyncio
async def test_generate_returns_reply(client: AsyncClient) -> None:
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService", _mock_ms_docs()),
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Hi Alex, here is the fix...")
        mock_llm_cls.return_value = mock_llm

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
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService", _mock_ms_docs()),
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            side_effect=ConnectionError("Ollama service unreachable at http://localhost:11434")
        )
        mock_llm_cls.return_value = mock_llm

        response = await client.post("/generate", json={
            "ticket_subject": "Test",
            "ticket_description": "Test description",
        })
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_generate_with_web_context(client: AsyncClient) -> None:
    """MS Learn docs should appear in the prompt sent to the LLM."""
    web_docs = [
        WebContextDoc(title="802.1X Setup Guide", url="https://learn.microsoft.com/802x", content="Enable 802.1X via Group Policy."),
    ]
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService") as mock_ms_cls,
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Here is the fix.")
        mock_llm_cls.return_value = mock_llm

        mock_ms = MagicMock()
        mock_ms.search = AsyncMock(return_value=web_docs)
        mock_ms_cls.return_value = mock_ms

        response = await client.post("/generate", json={
            "ticket_subject": "802.1X not working",
            "category": "NETWORK CONNECTION",
            "include_web_context": True,
        })
        assert response.status_code == 200

        # Verify the web context was included in the prompt
        prompt_arg = mock_llm.generate.call_args.kwargs["prompt"]
        assert "[WEB | Microsoft Learn]" in prompt_arg
        assert "802.1X Setup Guide" in prompt_arg
        assert "Enable 802.1X via Group Policy." in prompt_arg


@pytest.mark.asyncio
async def test_generate_web_context_disabled(client: AsyncClient) -> None:
    """When include_web_context is false, MicrosoftDocsService.search should not be called."""
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService") as mock_ms_cls,
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Reply without web context.")
        mock_llm_cls.return_value = mock_llm

        mock_ms = MagicMock()
        mock_ms.search = AsyncMock(return_value=[])
        mock_ms_cls.return_value = mock_ms

        response = await client.post("/generate", json={
            "ticket_subject": "Test",
            "ticket_description": "Test",
            "include_web_context": False,
        })
        assert response.status_code == 200
        mock_ms.search.assert_not_called()


@pytest.mark.asyncio
async def test_generate_web_context_failure_still_generates(client: AsyncClient) -> None:
    """If MS Learn search returns empty (graceful degradation), reply should still be generated."""
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService") as mock_ms_cls,
    ):
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Reply without web context.")
        mock_llm_cls.return_value = mock_llm

        mock_ms = MagicMock()
        mock_ms.search = AsyncMock(return_value=[])
        mock_ms_cls.return_value = mock_ms

        response = await client.post("/generate", json={
            "ticket_subject": "VPN issue",
            "category": "Network",
        })
        assert response.status_code == 200
        assert response.json()["reply"] == "Reply without web context."


@pytest.mark.asyncio
async def test_generate_ms_docs_config_disabled(client: AsyncClient) -> None:
    """When settings.microsoft_docs_enabled is False, search should not be called."""
    with (
        patch("app.routers.generate.RAGService") as mock_rag_cls,
        patch("app.routers.generate.LLMService") as mock_llm_cls,
        patch("app.routers.generate.MicrosoftDocsService") as mock_ms_cls,
        patch("app.routers.generate.settings") as mock_settings,
    ):
        mock_settings.microsoft_docs_enabled = False

        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[])
        mock_rag_cls.return_value = mock_rag

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="Reply with config disabled.")
        mock_llm_cls.return_value = mock_llm

        mock_ms = MagicMock()
        mock_ms.search = AsyncMock(return_value=[])
        mock_ms_cls.return_value = mock_ms

        response = await client.post("/generate", json={
            "ticket_subject": "Test",
            "include_web_context": True,
        })
        assert response.status_code == 200
        mock_ms.search.assert_not_called()
