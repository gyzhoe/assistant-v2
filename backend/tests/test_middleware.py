from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.helpers import setup_app_state


@pytest_asyncio.fixture
async def token_client() -> AsyncClient:
    """Client wired to an app instance with API token auth enabled."""
    with patch("app.config.settings.api_token", "test-secret"):
        token_app = create_app()
        token_app.state.chroma_client = MagicMock()
        token_app.state.llm_reachable = False
        setup_app_state(token_app)
        async with AsyncClient(
            transport=ASGITransport(app=token_app),
            base_url="http://testserver",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# API Token Authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_token_valid(token_client: AsyncClient) -> None:
    """Request with correct token should pass through."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Hello")
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])
    mock_embed = MagicMock()
    mock_embed.embed = AsyncMock(return_value=[0.1] * 768)

    # We need to set state on the token_client's app — access via the transport
    transport = token_client._transport
    assert hasattr(transport, "app")
    test_app = transport.app  # type: ignore[union-attr]
    test_app.state.rag_service = mock_rag
    test_app.state.llm_service = mock_llm
    test_app.state.ms_docs_service = mock_ms
    test_app.state.embed_service = mock_embed

    resp = await token_client.post(
        "/generate",
        json={"ticket_subject": "Test", "ticket_description": "Test desc"},
        headers={"X-Extension-Token": "test-secret"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_token_invalid(token_client: AsyncClient) -> None:
    """Request with wrong token should return 401."""
    resp = await token_client.post(
        "/generate",
        json={"ticket_subject": "Test", "ticket_description": "desc"},
        headers={"X-Extension-Token": "wrong-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_token_missing(token_client: AsyncClient) -> None:
    """Request without token should return 401 when token is configured."""
    resp = await token_client.post(
        "/generate",
        json={"ticket_subject": "Test", "ticket_description": "desc"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_token_exempt_health(token_client: AsyncClient) -> None:
    """/health should be accessible without a token."""
    resp = await token_client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_token_disabled(client: AsyncClient) -> None:
    """When api_token is empty (default), all requests pass through."""
    resp = await client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient) -> None:
    """All security headers should be present on responses."""
    resp = await client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
