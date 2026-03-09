"""Tests for retry logic in EmbedService.embed() and LLMService.generate().

Covers Q9 findings:
- Transient ConnectionErrors trigger retries
- Retries succeed on the Nth attempt
- Non-transient LLMModelErrors are NOT retried
- Max retries is respected
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.constants import LLM_MAX_RETRIES, LLMModelError
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService


def _ok_embed_response() -> MagicMock:
    """Build a mock httpx.Response for a successful embed call."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"data": [{"embedding": [0.1] * 768}]}
    return resp


def _ok_llm_response(content: str = "Hello") -> MagicMock:
    """Build a mock httpx.Response for a successful LLM generate call."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _http_error_response(status_code: int = 400) -> MagicMock:
    """Build a mock httpx.Response that raises HTTPStatusError on raise_for_status."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"HTTP {status_code}", request=MagicMock(), response=resp,
    )
    return resp


# ---------------------------------------------------------------------------
# EmbedService retry tests
# ---------------------------------------------------------------------------


class TestEmbedRetry:
    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        """Verify EmbedService retries transient ConnectionErrors."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = EmbedService(client=mock_client)

        # First call raises ConnectError, second succeeds
        mock_client.post.side_effect = [
            httpx.ConnectError("Connection refused"),
            _ok_embed_response(),
        ]

        with patch("app.services.embed_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.embed("test query")

        assert len(result) == 768
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_succeeds_on_third_attempt(self) -> None:
        """Verify embed succeeds after failing twice."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = EmbedService(client=mock_client)

        mock_client.post.side_effect = [
            httpx.ConnectError("down"),
            httpx.ConnectError("still down"),
            _ok_embed_response(),
        ]

        with patch("app.services.embed_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.embed("test query")

        assert len(result) == 768
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_model_error(self) -> None:
        """Verify LLMModelError is raised immediately without retry."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = EmbedService(client=mock_client)

        mock_client.post.return_value = _http_error_response(400)

        with pytest.raises(LLMModelError):
            await service.embed("test query")

        # Only one attempt — no retries for model errors
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self) -> None:
        """Verify ConnectionError raised after max retries are exhausted."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = EmbedService(client=mock_client)

        mock_client.post.side_effect = httpx.ConnectError("always down")

        with (
            patch("app.services.embed_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ConnectionError),
        ):
            await service.embed("test query")

        # 1 initial + LLM_MAX_RETRIES retries
        assert mock_client.post.call_count == 1 + LLM_MAX_RETRIES

    @pytest.mark.asyncio
    async def test_timeout_triggers_retry(self) -> None:
        """Verify httpx.TimeoutException is retried as a ConnectionError."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        service = EmbedService(client=mock_client)

        mock_client.post.side_effect = [
            httpx.ReadTimeout("timed out"),
            _ok_embed_response(),
        ]

        with patch("app.services.embed_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.embed("test query")

        assert len(result) == 768
        assert mock_client.post.call_count == 2


# ---------------------------------------------------------------------------
# LLMService retry tests
# ---------------------------------------------------------------------------


class TestLLMRetry:
    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        """Verify LLMService.generate retries transient ConnectionErrors."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.base_url = httpx.URL("http://localhost:11435")
        service = LLMService(client=mock_client)

        mock_client.post.side_effect = [
            httpx.ConnectError("Connection refused"),
            _ok_llm_response(),
        ]

        with patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock):
            result = await service.generate("prompt", "qwen3.5:9b")

        assert result == "Hello"
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_model_error(self) -> None:
        """Verify LLMModelError is raised immediately without retry."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.base_url = httpx.URL("http://localhost:11435")
        service = LLMService(client=mock_client)

        mock_client.post.return_value = _http_error_response(404)

        with pytest.raises(LLMModelError):
            await service.generate("prompt", "qwen3.5:9b")

        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self) -> None:
        """Verify ConnectionError raised after max retries are exhausted."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.base_url = httpx.URL("http://localhost:11435")
        service = LLMService(client=mock_client)

        mock_client.post.side_effect = httpx.ConnectError("always down")

        with (
            patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ConnectionError),
        ):
            await service.generate("prompt", "qwen3.5:9b")

        assert mock_client.post.call_count == 1 + LLM_MAX_RETRIES
