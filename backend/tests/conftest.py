from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.rag_service import RAGService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async httpx client wired to the FastAPI app.

    ASGITransport does not run the FastAPI lifespan, so we manually set
    app.state attributes that routers depend on.  Tests that exercise
    the generate router patch service instances at the app.state level, so
    the mock chroma_client placed here is never forwarded to real ChromaDB.
    """
    mock_ollama_client = MagicMock()
    mock_sync_client = MagicMock()

    app.state.chroma_client = MagicMock()
    app.state.ollama_reachable = False
    app.state.llm_service = LLMService(client=mock_ollama_client)
    app.state.embed_service = EmbedService(client=mock_ollama_client)
    app.state.sync_embed_service = EmbedService(client=mock_sync_client)
    app.state.ms_docs_service = MicrosoftDocsService(client=mock_ollama_client)
    app.state.rag_service = RAGService(
        chroma_client=app.state.chroma_client,
        embed_svc=app.state.embed_service,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
