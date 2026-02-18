import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.models.response_models import ContextDoc
from app.services.rag_service import RAGService


def make_mock_chroma() -> MagicMock:
    client = MagicMock()
    client.list_collections.return_value = []
    client.get_collection.side_effect = Exception("Collection not found")
    return client


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_no_collections() -> None:
    chroma = make_mock_chroma()
    with patch.object(RAGService, "embed_svc") as mock_embed:
        svc = RAGService(chroma_client=chroma)
        svc.embed_svc = MagicMock()
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

    svc = RAGService(chroma_client=chroma)
    svc.embed_svc = MagicMock()
    svc.embed_svc.embed = AsyncMock(return_value=[0.1] * 768)

    results = await svc.retrieve("network drive issue", max_docs=3)
    assert len(results) <= 3
    # KB article has lower distance (0.1) → higher score
    assert results[0].source == "kb"
    assert results[0].score > results[1].score
