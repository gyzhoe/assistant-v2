"""Tests for the SSE streaming generate endpoint and related helpers."""

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.constants import LLMModelError
from app.main import create_app
from app.models.response_models import ErrorCode
from app.services.microsoft_docs import WebContextDoc
from tests.helpers import setup_app_state


def _mock_ms_docs(return_value: list[WebContextDoc] | None = None) -> MagicMock:
    mock_instance = MagicMock()
    mock_instance.search = AsyncMock(return_value=return_value or [])
    return mock_instance


def _parse_sse_events(text: str) -> list[dict[str, object]]:
    """Parse SSE text into a list of JSON event dicts."""
    events: list[dict[str, object]] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest_asyncio.fixture
async def stream_app() -> Any:
    """Fresh app instance for stream tests — avoids rate-limit collisions."""
    app = create_app()
    setup_app_state(app)
    return app


@pytest_asyncio.fixture
async def stream_client(stream_app: Any) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=stream_app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Happy path: streaming returns meta + tokens + done
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_returns_sse_events(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """POST /generate with stream=true returns SSE meta, token, done events."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def fake_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "Hello"
        yield " world"

    mock_llm.generate_stream = fake_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "VPN Issue",
        "ticket_description": "Cannot connect",
        "stream": True,
    })
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse_events(response.text)
    assert len(events) == 4  # meta + 2 tokens + done

    assert events[0]["type"] == "meta"
    assert "context_docs" in events[0]

    assert events[1]["type"] == "token"
    assert events[1]["content"] == "Hello"

    assert events[2]["type"] == "token"
    assert events[2]["content"] == " world"

    assert events[3]["type"] == "done"
    assert "latency_ms" in events[3]


# ---------------------------------------------------------------------------
# SSE error mid-stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_connection_error_yields_error_event(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """If LLM connection fails during streaming, an error SSE event is emitted."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def failing_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "partial"
        raise ConnectionError("LLM server unreachable")

    mock_llm.generate_stream = failing_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == ErrorCode.LLM_DOWN.value

    # No done event after error
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 0


@pytest.mark.asyncio
async def test_stream_model_error_yields_error_event(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """LLMModelError during streaming yields an error SSE event."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def failing_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        raise LLMModelError("Model not found", status_code=404)
        yield  # make it a generator  # pragma: no cover

    mock_llm.generate_stream = failing_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == ErrorCode.MODEL_ERROR.value


# ---------------------------------------------------------------------------
# Streaming with empty token stream (LLM returns nothing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_empty_response(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """If LLM yields no tokens, stream contains meta + done only."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def empty_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        return
        yield  # make it a generator  # pragma: no cover

    mock_llm.generate_stream = empty_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "done"
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 0


# ---------------------------------------------------------------------------
# Streaming with context docs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_meta_contains_context_docs(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """The meta SSE event contains the RAG context documents."""
    from app.models.response_models import ContextDoc

    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[
        ContextDoc(content="Reset VPN", source="kb", score=0.85, metadata={}),
    ])
    mock_llm = MagicMock()

    async def fake_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "Fix"

    mock_llm.generate_stream = fake_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "VPN Issue",
        "stream": True,
    })
    events = _parse_sse_events(response.text)
    meta = events[0]
    assert meta["type"] == "meta"
    docs = meta["context_docs"]
    assert len(docs) == 1
    assert docs[0]["content"] == "Reset VPN"
    assert docs[0]["source"] == "kb"


# ---------------------------------------------------------------------------
# Non-streaming still works (regression)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_streaming_still_returns_json(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """POST /generate with stream=false returns JSON (backward compat)."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Fix applied.")
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "VPN Issue",
        "stream": False,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Fix applied."
    assert "application/json" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# Streaming logs stream flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_log_includes_stream_flag(
    stream_app: Any,
    stream_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Generate request log should include stream=True."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def fake_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "token"

    mock_llm.generate_stream = fake_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    with caplog.at_level(logging.INFO, logger="app.routers.generate"):
        await stream_client.post("/generate", json={
            "ticket_subject": "Test",
            "stream": True,
        })

    log_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "stream=True" in log_messages


# ---------------------------------------------------------------------------
# SSE headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_response_headers(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """SSE response should have correct cache and buffering headers."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def fake_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "x"

    mock_llm.generate_stream = fake_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# [H1] Context prep failure returns SSE error (not JSON)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_context_prep_failure_returns_sse_error(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """If _prepare_context fails, streaming returns SSE error, not JSON 503."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(
        side_effect=ConnectionError("Embed server down"),
    )
    mock_llm = MagicMock()
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    # Should still be 200 with SSE content type, not 503 JSON
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse_events(response.text)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["error_code"] == ErrorCode.LLM_DOWN.value
    assert "Embed server down" in str(events[0]["message"])


# ---------------------------------------------------------------------------
# [M4] Generic exception during streaming yields INTERNAL_ERROR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_unexpected_error_yields_internal_error(
    stream_app: Any, stream_client: AsyncClient,
) -> None:
    """An unexpected exception during streaming yields INTERNAL_ERROR SSE event."""
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()

    async def exploding_stream(prompt: str, model: str):  # noqa: ANN202, ARG001
        yield "partial"
        raise RuntimeError("something unexpected broke")

    mock_llm.generate_stream = exploding_stream
    mock_ms = _mock_ms_docs()

    stream_app.state.rag_service = mock_rag
    stream_app.state.llm_service = mock_llm
    stream_app.state.ms_docs_service = mock_ms

    response = await stream_client.post("/generate", json={
        "ticket_subject": "Test",
        "stream": True,
    })
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["error_code"] == ErrorCode.INTERNAL_ERROR.value

    # No done event after error
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 0
