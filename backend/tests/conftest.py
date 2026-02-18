from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async httpx client wired to the FastAPI app.

    ASGITransport does not run the FastAPI lifespan, so we manually set
    app.state attributes that routers depend on.  Tests that exercise
    the generate router patch RAGService/LLMService at the class level, so
    the mock chroma_client placed here is never forwarded to real ChromaDB.
    """
    app.state.chroma_client = MagicMock()
    app.state.ollama_reachable = False
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
