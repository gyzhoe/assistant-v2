"""Tests for global exception handlers registered in app.main."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.constants import LLMModelError
from app.main import create_app
from app.models.response_models import ErrorCode
from tests.helpers import setup_app_state


def _make_app_and_client() -> tuple[object, AsyncClient]:
    app = create_app()
    setup_app_state(app)
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )
    return app, client


# ---------------------------------------------------------------------------
# ConnectionError → 503 with LLM_DOWN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_returns_503() -> None:
    """ConnectionError raised in a route → 503 with ErrorCode.LLM_DOWN."""
    app, client = _make_app_and_client()

    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        side_effect=ConnectionError("LLM server unreachable"),
    )
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])

    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms

    async with client:
        response = await client.post("/generate", json={
            "ticket_subject": "Test",
        })

    assert response.status_code == 503
    data = response.json()
    assert data["error_code"] == ErrorCode.LLM_DOWN.value
    assert "message" in data


# ---------------------------------------------------------------------------
# LLMModelError → 502 with MODEL_ERROR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_model_error_returns_502() -> None:
    """LLMModelError raised in a route → 502 with ErrorCode.MODEL_ERROR."""
    app, client = _make_app_and_client()

    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        side_effect=LLMModelError("Model not found", status_code=404),
    )
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])

    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms

    async with client:
        response = await client.post("/generate", json={
            "ticket_subject": "Test",
        })

    assert response.status_code == 502
    data = response.json()
    assert data["error_code"] == ErrorCode.MODEL_ERROR.value
    assert "Model not found" in data["message"]


# ---------------------------------------------------------------------------
# Generic Exception → 500 with INTERNAL_ERROR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_exception_returns_500() -> None:
    """Unhandled exception → 500 with ErrorCode.INTERNAL_ERROR.

    Uses a dedicated route that raises a plain RuntimeError to test the
    UnhandledExceptionMiddleware catch-all.
    """
    test_app = create_app()
    setup_app_state(test_app)

    @test_app.get("/test-crash")
    async def crash_route() -> None:
        msg = "unexpected crash"
        raise RuntimeError(msg)

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as test_client:
        response = await test_client.get("/test-crash")

    assert response.status_code == 500
    data = response.json()
    assert data["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert data["message"] == "Internal server error"


# ---------------------------------------------------------------------------
# ErrorResponse shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_response_has_correct_shape() -> None:
    """All error responses must have exactly 'message' and 'error_code'."""
    app, client = _make_app_and_client()

    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        side_effect=ConnectionError("down"),
    )
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])

    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms

    async with client:
        response = await client.post("/generate", json={
            "ticket_subject": "Test",
        })

    data = response.json()
    assert set(data.keys()) == {"message", "error_code"}
