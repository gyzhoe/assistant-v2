from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 1.0


class EmbedService:
    """Generates embeddings using nomic-embed-text via Ollama.

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
        self._base_url = settings.ollama_base_url
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
        """Return the embedding vector with retry logic (async path)."""
        last_error: ConnectionError | None = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                if isinstance(self._client, httpx.AsyncClient):
                    result = await self._embed_async(text)
                else:
                    result = await asyncio.to_thread(self._embed_sync, text)
                if attempt > 0:
                    logger.info("Ollama embed succeeded on attempt %d", attempt + 1)
                return result
            except ConnectionError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Ollama embed attempt %d failed, retrying in %.1fs: %s",
                        attempt + 1, RETRY_DELAY, exc,
                    )
                    await asyncio.sleep(RETRY_DELAY)
        logger.error("Ollama embed failed after %d attempts", 1 + MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    async def _embed_async(self, text: str) -> list[float]:
        assert isinstance(self._client, httpx.AsyncClient)
        try:
            resp = await self._client.post(
                "/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
            if "embedding" not in data:
                raise ConnectionError(
                    f"Ollama embed response missing 'embedding' key: {list(data.keys())}"
                )
            return list(data["embedding"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Ollama embed service unreachable at {self._base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"Ollama embed request timed out at {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Ollama embed returned error {exc.response.status_code}"
            ) from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise ConnectionError(
                f"Ollama embed response invalid or missing expected key: {exc}"
            ) from exc

    def _embed_sync(self, text: str) -> list[float]:
        assert isinstance(self._client, httpx.Client)
        try:
            resp = self._client.post(
                "/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            data = resp.json()
            if "embedding" not in data:
                raise ConnectionError(
                    f"Ollama embed response missing 'embedding' key: {list(data.keys())}"
                )
            return list(data["embedding"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Ollama embed service unreachable at {self._base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"Ollama embed request timed out at {self._base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Ollama embed returned error {exc.response.status_code}"
            ) from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise ConnectionError(
                f"Ollama embed response invalid or missing expected key: {exc}"
            ) from exc
