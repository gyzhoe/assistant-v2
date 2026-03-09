"""Unit tests for _prepare_context() in the generate router.

Covers Q10 findings:
- Pinned article fetching
- Web context integration
- Notes formatting in prompt
- RAG results and few-shot example interaction
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.request_models import GenerateRequest
from app.models.response_models import ContextDoc
from app.routers.generate import _prepare_context
from app.services.microsoft_docs import WebContextDoc
from tests.helpers import mock_ms_docs, setup_app_state


@pytest_asyncio.fixture
async def ctx_app() -> FastAPI:
    """Fresh app with mock services for _prepare_context tests."""
    app = create_app()
    setup_app_state(app)
    return app


@pytest_asyncio.fixture
async def ctx_client(ctx_app: FastAPI) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=ctx_app),
        base_url="http://testserver",
    ) as ac:
        yield ac


def _make_request(ctx_app: FastAPI) -> MagicMock:
    """Create a mock Request object with app.state wired up."""
    request = MagicMock()
    request.app = ctx_app
    return request


@pytest.mark.asyncio
async def test_prepare_context_returns_context_docs(ctx_app: FastAPI) -> None:
    """Basic call returns context docs, prompt string, and web count."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[
        ContextDoc(content="Reset VPN config", source="kb", score=0.85, metadata={}),
    ])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    body = GenerateRequest(ticket_subject="VPN Issue")
    request = _make_request(ctx_app)

    context_docs, prompt, web_count = await _prepare_context(body, request)

    assert len(context_docs) == 1
    assert context_docs[0].content == "Reset VPN config"
    assert "Reset VPN config" in prompt
    assert web_count == 0


@pytest.mark.asyncio
async def test_prepare_context_with_pinned_articles(ctx_app: FastAPI) -> None:
    """Pinned articles are prepended to context docs."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[
        ContextDoc(content="RAG result", source="kb", score=0.7, metadata={}),
    ])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    # Mock ChromaDB to return a pinned article
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "documents": ["Pinned KB content"],
        "metadatas": [{"article_id": "art-1", "title": "Pinned Article"}],
    }
    ctx_app.state.chroma_client.get_collection.return_value = mock_col

    body = GenerateRequest(
        ticket_subject="VPN Issue",
        pinned_article_ids=["art-1"],
    )
    request = _make_request(ctx_app)

    context_docs, prompt, _ = await _prepare_context(body, request)

    # Pinned doc should be first
    assert len(context_docs) == 2
    assert context_docs[0].content == "Pinned KB content"
    assert context_docs[0].metadata.get("source_type") == "pinned"
    assert context_docs[1].content == "RAG result"

    # Prompt should contain PINNED label
    assert "PINNED" in prompt


@pytest.mark.asyncio
async def test_prepare_context_with_web_docs(ctx_app: FastAPI) -> None:
    """Web docs are included when include_web_context is True."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag

    web_docs = [
        WebContextDoc(
            title="VPN Guide",
            url="https://learn.microsoft.com/vpn",
            content="Configure VPN via GP.",
        ),
    ]
    ctx_app.state.ms_docs_service = mock_ms_docs(return_value=web_docs)

    body = GenerateRequest(
        ticket_subject="VPN Issue",
        category="Network",
        include_web_context=True,
    )
    request = _make_request(ctx_app)

    with patch("app.routers.generate.settings") as mock_settings:
        mock_settings.microsoft_docs_enabled = True
        mock_settings.environment_context = ""
        context_docs, prompt, web_count = await _prepare_context(body, request)

    assert web_count == 1
    assert "[WEB | Microsoft Learn]" in prompt
    assert "VPN Guide" in prompt
    assert "Configure VPN via GP." in prompt


@pytest.mark.asyncio
async def test_prepare_context_with_notes(ctx_app: FastAPI) -> None:
    """Notes appear in the prompt as conversation history."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    body = GenerateRequest(
        ticket_subject="VPN Issue",
        notes=[
            {"text": "VPN keeps dropping", "author": "User", "type": "client", "date": "2026-03-01"},
            {"text": "Checked config", "author": "Tech", "type": "tech_visible", "date": "2026-03-02"},
        ],
    )
    request = _make_request(ctx_app)

    _, prompt, _ = await _prepare_context(body, request)

    assert "Ticket Conversation History" in prompt
    assert "VPN keeps dropping" in prompt
    assert "Checked config" in prompt


@pytest.mark.asyncio
async def test_prepare_context_without_notes(ctx_app: FastAPI) -> None:
    """Without notes, prompt does not contain conversation history section."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    body = GenerateRequest(ticket_subject="VPN Issue")
    request = _make_request(ctx_app)

    _, prompt, _ = await _prepare_context(body, request)

    assert "Ticket Conversation History" not in prompt


@pytest.mark.asyncio
async def test_prepare_context_web_disabled_by_settings(ctx_app: FastAPI) -> None:
    """Web docs not fetched when microsoft_docs_enabled is False."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag

    mock_ms = mock_ms_docs()
    ctx_app.state.ms_docs_service = mock_ms

    body = GenerateRequest(
        ticket_subject="VPN Issue",
        include_web_context=True,
    )
    request = _make_request(ctx_app)

    with patch("app.routers.generate.settings") as mock_settings:
        mock_settings.microsoft_docs_enabled = False
        mock_settings.environment_context = ""
        _, _, web_count = await _prepare_context(body, request)

    assert web_count == 0
    mock_ms.search.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_context_prompt_suffix_appended(ctx_app: FastAPI) -> None:
    """prompt_suffix is appended to the prompt wrapped in XML tags.

    Note: prompt_suffix wrapping happens in generate_reply(), not _prepare_context().
    This test verifies _prepare_context produces a valid base prompt.
    """
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    body = GenerateRequest(
        ticket_subject="VPN Issue",
        prompt_suffix="Be concise",
    )
    request = _make_request(ctx_app)

    _, prompt, _ = await _prepare_context(body, request)

    # _prepare_context appends prompt_suffix
    assert "<user_additional_instructions>" in prompt
    assert "Be concise" in prompt


@pytest.mark.asyncio
async def test_prepare_context_few_shot_from_rated_replies(ctx_app: FastAPI) -> None:
    """Dynamic few-shot examples from rated_replies appear in prompt."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    ctx_app.state.rag_service = mock_rag
    ctx_app.state.ms_docs_service = mock_ms_docs()

    # Mock rated_replies collection
    mock_col = MagicMock()
    mock_col.count.return_value = 1
    mock_col.query.return_value = {
        "documents": [["VPN disconnects frequently"]],
        "metadatas": [[{
            "ticket_subject": "VPN drops",
            "reply": "Clear VPN credentials and reconnect.",
            "rating": "good",
        }]],
        "distances": [[0.2]],  # distance 0.2 = similarity 0.8
    }

    def get_collection(name: str) -> MagicMock:
        if name == "rated_replies":
            return mock_col
        raise ValueError(f"Unknown collection: {name}")

    ctx_app.state.chroma_client.get_collection.side_effect = get_collection

    body = GenerateRequest(ticket_subject="VPN Issue", category="Network")
    request = _make_request(ctx_app)

    _, prompt, _ = await _prepare_context(body, request)

    assert "real validated reply" in prompt
    assert "VPN drops" in prompt
    assert "Clear VPN credentials" in prompt
