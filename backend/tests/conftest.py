import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import setup_app_state


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
    setup_app_state(app)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
