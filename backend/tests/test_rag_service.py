from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rag_service import RAGService


def make_mock_chroma() -> MagicMock:
    client = MagicMock()
    client.list_collections.return_value = []
    client.get_collection.side_effect = Exception("Collection not found")
    return client


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_collections() -> None:
    chroma = make_mock_chroma()
    mock_embed = MagicMock()
    svc = RAGService(chroma_client=chroma, embed_svc=mock_embed)
    svc.embed_svc.embed = AsyncMock(return_value=[0.1] * 768)
    results = await svc.retrieve("test query", max_docs=5)
    assert results == []


@pytest.mark.asyncio
async def test_retrieve_merges_and_ranks() -> None:
    chroma = MagicMock()

    kb_col = MagicMock()
    kb_col.count.return_value = 2
    kb_col.query.return_value = {
        "documents": [["KB article content"]],
        "metadatas": [[ {"article_id": "KB-1"}]],
        "distances": [[0.1]],
    }

    ticket_col = MagicMock()
    ticket_col.count.return_value = 1
    ticket_col.query.return_value = {
        "documents": [["Ticket content"]],
        "metadatas": [[{"ticket_id": "T-100"}]],
        "distances": [[0.3]],
    }

    def get_collection(name: str) -> MagicMock:
        if name == "kb_articles":
            return kb_col
        return ticket_col

    chroma.get_collection.side_effect = get_collection

    mock_embed = MagicMock()
    svc = RAGService(chroma_client=chroma, embed_svc=mock_embed)
    svc.embed_svc.embed = AsyncMock(return_value=[0.1] * 768)

    results = await svc.retrieve("network drive issue", max_docs=3)
    assert len(results) <= 3
    # KB article has lower distance (0.1) → higher score
    assert results[0].source == "kb"
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_retrieve_filters_low_similarity_docs() -> None:
    """Documents below rag_min_similarity threshold should be filtered out."""
    chroma = MagicMock()

    kb_col = MagicMock()
    kb_col.count.return_value = 2
    kb_col.query.return_value = {
        "documents": [["High score doc", "Low score doc"]],
        "metadatas": [[{"id": "1"}, {"id": "2"}]],
        "distances": [[0.1, 0.9]],  # scores: 0.9 and 0.1
    }

    ticket_col = MagicMock()
    ticket_col.count.return_value = 0

    def get_collection(name: str) -> MagicMock:
        if name == "kb_articles":
            return kb_col
        return ticket_col

    chroma.get_collection.side_effect = get_collection

    mock_embed = MagicMock()
    svc = RAGService(chroma_client=chroma, embed_svc=mock_embed)
    svc.embed_svc.embed = AsyncMock(return_value=[0.1] * 768)

    with patch("app.services.rag_service.settings") as mock_settings:
        mock_settings.rag_min_similarity = 0.35
        results = await svc.retrieve("test query", max_docs=5)

    # Only the high-score doc (0.9) should remain; low-score (0.1) is filtered
    assert len(results) == 1
    assert results[0].content == "High score doc"
    assert results[0].score >= 0.35


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_all_below_threshold() -> None:
    """When all docs are below the threshold, an empty list is returned."""
    chroma = MagicMock()

    kb_col = MagicMock()
    kb_col.count.return_value = 1
    kb_col.query.return_value = {
        "documents": [["Irrelevant doc"]],
        "metadatas": [[{"id": "1"}]],
        "distances": [[0.8]],  # score: 0.2
    }

    ticket_col = MagicMock()
    ticket_col.count.return_value = 1
    ticket_col.query.return_value = {
        "documents": [["Another irrelevant doc"]],
        "metadatas": [[{"id": "2"}]],
        "distances": [[0.9]],  # score: 0.1
    }

    def get_collection(name: str) -> MagicMock:
        if name == "kb_articles":
            return kb_col
        return ticket_col

    chroma.get_collection.side_effect = get_collection

    mock_embed = MagicMock()
    svc = RAGService(chroma_client=chroma, embed_svc=mock_embed)
    svc.embed_svc.embed = AsyncMock(return_value=[0.1] * 768)

    with patch("app.services.rag_service.settings") as mock_settings:
        mock_settings.rag_min_similarity = 0.35
        results = await svc.retrieve("test query", max_docs=5)

    assert results == []
