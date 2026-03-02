"""Tests for pinned article injection in the generate endpoint."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.main import app


def _mock_chroma_with_pinned(article_id: str, text: str, title: str) -> MagicMock:
    """Create a mock chroma_client that returns pinned article data."""
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": [f"{article_id}_chunk_0"],
        "documents": [text],
        "metadatas": [
            {"article_id": article_id, "title": title, "source_type": "html"},
        ],
    }
    mock_client = MagicMock()
    mock_client.get_collection.return_value = mock_col
    return mock_client


@pytest.mark.asyncio
async def test_generate_no_pinned_articles_works_normally(client: AsyncClient) -> None:
    """Sending pinned_article_ids=[] should not change behavior."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Normal reply.")
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])

    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms

    response = await client.post("/generate", json={
        "ticket_subject": "Test ticket",
        "ticket_description": "Something is broken",
        "pinned_article_ids": [],
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "Normal reply."


@pytest.mark.asyncio
async def test_generate_with_pinned_article_injects_context(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pinned article should appear in prompt with PINNED label."""
    pinned_id = "abc123"
    pinned_text = "Reset the VPN credentials using Credential Manager."
    pinned_title = "VPN Reset Guide"

    # Use monkeypatch so app.state.chroma_client is restored after the test
    monkeypatch.setattr(
        app.state, "chroma_client",
        _mock_chroma_with_pinned(pinned_id, pinned_text, pinned_title),
    )

    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Reply with pinned context.")
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])
    mock_embed = MagicMock()
    mock_embed.embed = AsyncMock(return_value=[0.1] * 768)

    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms
    app.state.embed_service = mock_embed

    response = await client.post("/generate", json={
        "ticket_subject": "VPN issue",
        "ticket_description": "VPN disconnects",
        "pinned_article_ids": [pinned_id],
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "Reply with pinned context."

    # Verify the pinned text was included in the prompt
    prompt_arg = mock_llm.generate.call_args.kwargs["prompt"]
    assert "PINNED" in prompt_arg
    assert pinned_text in prompt_arg

    # Verify pinned doc is in context_docs response
    context_docs = response.json()["context_docs"]
    assert len(context_docs) >= 1
    pinned_doc = context_docs[0]
    assert pinned_doc["source"] == "kb"
    assert pinned_doc["score"] == 1.0
    assert pinned_doc["metadata"]["source_type"] == "pinned"
