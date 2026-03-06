from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import httpx

from app.config import settings
from app.constants import LLM_MAX_RETRIES, LLM_RETRY_DELAY, LLMModelError

logger = logging.getLogger(__name__)


class EmbedService:
    """Generates embeddings via llama.cpp's OpenAI-compatible embeddings API.

    Accepts both async and sync httpx clients:
    - ``httpx.AsyncClient`` for async route handlers (``embed()`` method)
    - ``httpx.Client`` for sync ingestion pipelines (``embed_fn`` property)
    """

    def __init__(
        self,
        client: httpx.AsyncClient | httpx.Client,
        model: str = "nomic-embed-text",
    ) -> None:
        self.model = model
        self._client = client

    @property
    def embed_fn(self) -> Callable[[str], list[float]]:
        """Public accessor for the synchronous embed function.

        Only usable when the service was initialised with an ``httpx.Client``.
        Raises ``TypeError`` if the underlying client is async.
        """
        if isinstance(self._client, httpx.AsyncClient):
            raise TypeError(
                "embed_fn (sync) is not available on an async EmbedService. "
                "Use embed() instead, or create a separate EmbedService "
                "with an httpx.Client for sync pipelines."
            )
        return self._embed_sync

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector with retry logic (async path).

        Raises:
            ConnectionError: Embed server is unreachable (retried).
            LLMModelError: Embed server returned an HTTP error (not retried).
        """
        last_error: ConnectionError | None = None
        for attempt in range(1 + LLM_MAX_RETRIES):
            try:
                if isinstance(self._client, httpx.AsyncClient):
                    result = await self._embed_async(text)
                else:
                    result = await asyncio.to_thread(self._embed_sync, text)
                if attempt > 0:
                    logger.info("Embed succeeded on attempt %d", attempt + 1)
                return result
            except LLMModelError:
                raise  # Model/API errors are not transient — don't retry
            except ConnectionError as exc:
                last_error = exc
                if attempt < LLM_MAX_RETRIES:
                    logger.warning(
                        "Embed attempt %d failed, retrying in %.1fs: %s",
                        attempt + 1, LLM_RETRY_DELAY, exc,
                    )
                    await asyncio.sleep(LLM_RETRY_DELAY)
        logger.error("Embed failed after %d attempts", 1 + LLM_MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    def _parse_embed_response(self, resp: httpx.Response) -> list[float]:
        """Parse and validate an embed response (shared by async and sync paths)."""
        resp.raise_for_status()
        data = resp.json()
        try:
            return list(data["data"][0]["embedding"])
        except (KeyError, IndexError):
            raise ConnectionError(
                f"Embed response missing expected key: {list(data.keys())}"
            )

    def _handle_request_error(self, exc: Exception) -> ConnectionError | LLMModelError:
        """Convert httpx exceptions to appropriate error types.

        Returns ``LLMModelError`` for HTTP status errors (model/API issues)
        and ``ConnectionError`` for connectivity/parsing issues.
        """
        base_url = settings.embed_base_url
        if isinstance(exc, httpx.ConnectError):
            return ConnectionError(f"Embed server unreachable at {base_url}")
        if isinstance(exc, httpx.TimeoutException):
            return ConnectionError(f"Embed request timed out at {base_url}")
        if isinstance(exc, httpx.HTTPStatusError):
            return LLMModelError(
                f"Embed server returned HTTP {exc.response.status_code} for model '{self.model}'",
                status_code=exc.response.status_code,
            )
        if isinstance(exc, (json.JSONDecodeError, KeyError)):
            return ConnectionError(
                f"Embed response invalid or missing expected key: {exc}"
            )
        return ConnectionError(str(exc))

    async def _embed_async(self, text: str) -> list[float]:
        assert isinstance(self._client, httpx.AsyncClient)
        try:
            resp = await self._client.post(
                "/v1/embeddings",
                json={"model": self.model, "input": text},
            )
            return self._parse_embed_response(resp)
        except ConnectionError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            raise self._handle_request_error(exc) from exc

    def _embed_sync(self, text: str) -> list[float]:
        assert isinstance(self._client, httpx.Client)
        try:
            resp = self._client.post(
                "/v1/embeddings",
                json={"model": self.model, "input": text},
            )
            return self._parse_embed_response(resp)
        except ConnectionError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            raise self._handle_request_error(exc) from exc
