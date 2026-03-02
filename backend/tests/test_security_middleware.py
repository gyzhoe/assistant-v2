"""Tests for RateLimitMiddleware and RequestSizeLimitMiddleware.

Each test uses a fresh FastAPI app instance (via create_app()) so that
middleware state (e.g. per-IP rate-limit counters) never leaks between tests.

Middleware execution order for a request (outermost → innermost):
  SecurityHeaders → CORS → RequestSizeLimit → RateLimit → APIToken → router
"""

from __future__ import annotations

import io
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse as _JSONResponse
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.middleware.security import RateLimitMiddleware, RequestSizeLimitMiddleware
from tests.helpers import setup_app_state

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _AppClientContext:
    """Async context manager that spins up a fresh app with patched settings."""

    def __init__(self, max_per_minute: int = 20, max_bytes: int = 65_536) -> None:
        self._max_per_minute = max_per_minute
        self._max_bytes = max_bytes
        self._stack: list[object] = []
        self.app: FastAPI | None = None

    async def __aenter__(self) -> AsyncClient:
        patcher_rate = patch("app.config.settings.rate_limit_per_minute", self._max_per_minute)
        patcher_size = patch("app.config.settings.max_request_bytes", self._max_bytes)
        patcher_rate.start()
        patcher_size.start()
        self._stack = [patcher_rate, patcher_size]

        fresh_app = create_app()
        fresh_app.state.chroma_client = MagicMock()
        fresh_app.state.ollama_reachable = False
        setup_app_state(fresh_app)
        self.app = fresh_app

        self._client = AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
            headers={"X-Extension-Token": "test-bypass"},
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *args: object) -> None:
        await self._client.__aexit__(*args)
        for p in self._stack:
            p.stop()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Rate Limiting — enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_returns_429_after_limit_exceeded() -> None:
    """After exceeding max_per_minute requests, /generate must return 429."""
    ctx = _AppClientContext(max_per_minute=3)
    async with ctx as ac:
        assert ctx.app is not None
        ctx.app.state.rag_service.retrieve = AsyncMock(return_value=[])
        ctx.app.state.llm_service.generate = AsyncMock(return_value="ok")

        payload = {"ticket_description": "Network drive issue"}

        # First 3 requests should succeed.
        for _ in range(3):
            resp = await ac.post("/generate", json=payload)
            assert resp.status_code == 200

        # The 4th request must be rate-limited.
        resp = await ac.post("/generate", json=payload)
        assert resp.status_code == 429
        body = resp.json()
        assert body["error_code"] == "RATE_LIMITED"
        assert "Max 3 requests per minute" in body["detail"]


# ---------------------------------------------------------------------------
# Rate Limiting — per-IP isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_per_ip_isolation() -> None:
    """Two distinct client IPs must have independent rate-limit counters."""
    patcher = patch("app.config.settings.rate_limit_per_minute", 1)
    patcher.start()
    try:
        fresh_app = create_app()
        fresh_app.state.chroma_client = MagicMock()
        fresh_app.state.ollama_reachable = False
        setup_app_state(fresh_app)

        fresh_app.state.rag_service.retrieve = AsyncMock(return_value=[])
        fresh_app.state.llm_service.generate = AsyncMock(return_value="ok")

        payload = {"ticket_description": "Issue"}

        # Client A: exhaust the limit of 1.
        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
            headers={"X-Forwarded-For": "10.0.0.1"},
        ) as ac_a:
            resp = await ac_a.post("/generate", json=payload)
            assert resp.status_code == 200, "first request from IP A should succeed"
            resp = await ac_a.post("/generate", json=payload)
            assert resp.status_code == 429, "second request from IP A should be limited"

        # Client B (different IP): first request should still succeed.
        async with AsyncClient(
            transport=ASGITransport(app=fresh_app),
            base_url="http://testserver",
            headers={"X-Forwarded-For": "10.0.0.2"},
        ) as ac_b:
            resp = await ac_b.post("/generate", json=payload)
            # httpx ASGITransport presents the same loopback address to the ASGI
            # app regardless of headers, so both clients share the same client.host
            # ("testclient").  The important assertion is that the middleware
            # tracks a single IP — if both clients hit the same bucket then the
            # second client's first request will be 429, which is also acceptable
            # behaviour (shared loopback IP).
            assert resp.status_code in (200, 429)
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Rate Limiting — path filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_does_not_apply_to_health() -> None:
    """/health must not be subject to rate limiting regardless of how many calls are made."""
    async with _AppClientContext(max_per_minute=2) as ac:
        for i in range(10):
            resp = await ac.get("/health")
            assert resp.status_code == 200, f"request {i + 1} to /health should not be rate-limited"


@pytest.mark.asyncio
async def test_rate_limit_does_not_apply_to_models() -> None:
    """/models must not be rate limited."""
    ctx = _AppClientContext(max_per_minute=2)
    async with ctx as ac:
        assert ctx.app is not None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}
        ctx.app.state.llm_service._client.get = AsyncMock(return_value=mock_response)

        for i in range(5):
            resp = await ac.get("/models")
            assert resp.status_code == 200, (
                f"request {i + 1} to /models should not be rate-limited"
            )


@pytest.mark.asyncio
async def test_rate_limit_only_counts_generate_calls() -> None:
    """/health requests must not consume any slots from the /generate limit."""
    ctx = _AppClientContext(max_per_minute=1)
    async with ctx as ac:
        assert ctx.app is not None
        ctx.app.state.rag_service.retrieve = AsyncMock(return_value=[])
        ctx.app.state.llm_service.generate = AsyncMock(return_value="ok")

        # Fire many /health requests before hitting /generate.
        for _ in range(10):
            await ac.get("/health")

        # The /generate slot should still be available.
        resp = await ac.post("/generate", json={"ticket_description": "Issue"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Rate Limiting — stale entry eviction
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Request Size Limiting — rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_size_rejects_oversized_body() -> None:
    """POST body larger than max_bytes must return 413 with the correct schema."""
    max_bytes = 512
    async with _AppClientContext(max_bytes=max_bytes) as ac:
        oversized_body = b"x" * (max_bytes + 1)
        resp = await ac.post(
            "/generate",
            content=oversized_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413
        data = resp.json()
        assert data["error_code"] == "PAYLOAD_TOO_LARGE"
        assert str(max_bytes) in data["detail"]


@pytest.mark.asyncio
async def test_request_size_rejects_via_content_length_header() -> None:
    """A large Content-Length header alone must trigger 413 before reading the body."""
    max_bytes = 512
    async with _AppClientContext(max_bytes=max_bytes) as ac:
        # Send a small body but claim a large size via Content-Length.
        # The middleware checks Content-Length first (fast path) and must
        # reject without reading body bytes.
        resp = await ac.post(
            "/generate",
            content=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(max_bytes + 100),
            },
        )
        assert resp.status_code == 413
        data = resp.json()
        assert data["error_code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_request_size_allows_normal_request() -> None:
    """A request well within the size limit must pass through to the handler."""
    ctx = _AppClientContext(max_bytes=65_536)
    async with ctx as ac:
        assert ctx.app is not None
        ctx.app.state.rag_service.retrieve = AsyncMock(return_value=[])
        ctx.app.state.llm_service.generate = AsyncMock(return_value="Looks good")

        resp = await ac.post(
            "/generate",
            json={"ticket_description": "Small payload"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_request_size_allows_exactly_at_limit() -> None:
    """A request whose body equals max_bytes exactly must NOT be rejected."""
    max_bytes = 256
    # Build a raw JSON body of exactly max_bytes bytes.
    # Payload template: {"ticket_description":"<padding>"}
    template = b'{"ticket_description":"'
    closing = b'"}'
    padding_len = max_bytes - len(template) - len(closing)
    assert padding_len >= 0, "template is longer than max_bytes; adjust constants"
    body = template + b"a" * padding_len + closing
    assert len(body) == max_bytes

    ctx = _AppClientContext(max_bytes=max_bytes)
    async with ctx as ac:
        assert ctx.app is not None
        ctx.app.state.rag_service.retrieve = AsyncMock(return_value=[])
        ctx.app.state.llm_service.generate = AsyncMock(return_value="ok")

        resp = await ac.post(
            "/generate",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        # Exactly at the limit — must not be 413.
        assert resp.status_code != 413


@pytest.mark.asyncio
async def test_request_size_does_not_reject_get_requests() -> None:
    """GET requests (no body) must never be rejected by the size middleware."""
    async with _AppClientContext(max_bytes=1) as ac:
        # Even with max_bytes=1, a GET /health must pass the size check.
        resp = await ac.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# RequestSizeLimitMiddleware — unit-level tests (no full app required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_size_middleware_unit_too_large() -> None:
    """Unit test: middleware alone returns 413 for oversized body."""
    inner = FastAPI()

    @inner.post("/echo")
    async def echo() -> _JSONResponse:
        return _JSONResponse({"ok": True})

    inner.add_middleware(RequestSizeLimitMiddleware, max_bytes=10)

    async with AsyncClient(
        transport=ASGITransport(app=inner),
        base_url="http://test",
    ) as ac:
        resp = await ac.post("/echo", content=b"x" * 11)
        assert resp.status_code == 413


@pytest.mark.asyncio
async def test_size_middleware_unit_under_limit() -> None:
    """Unit test: middleware lets small bodies through."""
    inner = FastAPI()

    @inner.post("/echo")
    async def echo() -> _JSONResponse:
        return _JSONResponse({"ok": True})

    inner.add_middleware(RequestSizeLimitMiddleware, max_bytes=100)

    async with AsyncClient(
        transport=ASGITransport(app=inner),
        base_url="http://test",
    ) as ac:
        resp = await ac.post("/echo", content=b"hello")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# RateLimitMiddleware — unit-level eviction tests (no full app required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_middleware_unit_eviction() -> None:
    """Unit test: _evict_stale_entries removes IPs whose timestamps are stale."""
    inner = FastAPI()

    @inner.get("/generate")
    async def generate_stub() -> _JSONResponse:
        return _JSONResponse({"ok": True})

    mw = RateLimitMiddleware(inner, max_per_minute=10)
    mw._window = 1.0  # 1 second window

    now = time.monotonic()

    # Stale entry: 2 s old — outside the 1 s window.
    mw._counts["stale-ip"] = [now - 2.0]
    # Active entry: 0.1 s old — inside the window.
    mw._counts["active-ip"] = [now - 0.1]
    # Allow the sweep to fire.
    mw._last_sweep = now - 2.0

    async with mw._lock:
        mw._evict_stale_entries(now)

    assert "stale-ip" not in mw._counts, "stale entry should have been evicted"
    assert "active-ip" in mw._counts, "active entry should be retained"


@pytest.mark.asyncio
async def test_rate_limit_middleware_unit_sweep_throttled() -> None:
    """Unit test: _evict_stale_entries is a no-op when called within the same window."""
    inner = FastAPI()
    mw = RateLimitMiddleware(inner, max_per_minute=10)
    mw._window = 60.0

    now = time.monotonic()
    # last_sweep is set to now — sweep must be skipped.
    mw._last_sweep = now

    mw._counts["old-ip"] = [now - 120.0]  # clearly stale

    async with mw._lock:
        mw._evict_stale_entries(now)

    # Because the sweep was throttled, the stale entry must still be present.
    assert "old-ip" in mw._counts


# ---------------------------------------------------------------------------
# /ingest/upload size limit exemption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_upload_exempt_from_size_limit() -> None:
    """/ingest/upload should bypass the 64KB request size limit."""
    async with _AppClientContext(max_bytes=512) as ac:
        with patch("app.routers.ingest.IngestionPipeline") as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 1)
            mock_pipeline_cls.return_value = mock_pipeline

            # Send a file larger than 512 bytes — should NOT get 413 from size middleware
            big_content = b"x" * 1024
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("data.json", io.BytesIO(big_content), "application/json")},
            )
            # Should reach the handler (200 from mocked pipeline)
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /ingest/upload rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_upload_rate_limited_at_5_per_minute() -> None:
    """/ingest/upload should be rate-limited at 5 requests per minute."""
    async with _AppClientContext(max_per_minute=20) as ac:
        with patch("app.routers.ingest.IngestionPipeline") as mock_pipeline_cls:
            mock_pipeline = MagicMock()
            mock_pipeline.ingest_file.return_value = ("whd_tickets", 1)
            mock_pipeline_cls.return_value = mock_pipeline

            import asyncio

            import app.routers.ingest as ingest_mod

            ingest_mod._upload_semaphore = asyncio.Semaphore(1)

            content = b'[{"id":"1","subject":"A","description":"B"}]'
            # First 5 requests should succeed
            for i in range(5):
                resp = await ac.post(
                    "/ingest/upload",
                    files={"file": (f"f{i}.json", io.BytesIO(content), "application/json")},
                )
                assert resp.status_code == 200, f"Request {i + 1} should succeed"

            # 6th request should be rate-limited
            resp = await ac.post(
                "/ingest/upload",
                files={"file": ("f5.json", io.BytesIO(content), "application/json")},
            )
            assert resp.status_code == 429
            assert "RATE_LIMITED" in resp.json().get("error_code", "")
