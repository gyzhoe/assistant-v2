import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.helpers import setup_app_state


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def test_app() -> FastAPI:
    """Fresh FastAPI app instance per test — fully isolated from other tests."""
    app = create_app()
    setup_app_state(app)
    return app


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncClient:
    """Async httpx client wired to a fresh FastAPI app.

    Each test gets its own app instance via the test_app fixture,
    so mutations to app.state never leak between tests.
    """
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as ac:
        yield ac
