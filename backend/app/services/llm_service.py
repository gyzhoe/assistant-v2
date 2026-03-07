import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.config import settings
from app.constants import LLM_MAX_RETRIES, LLM_RETRY_DELAY, LLMModelError

logger = logging.getLogger(__name__)


class LLMService:
    """Generates text completions via llama.cpp's OpenAI-compatible API."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        """Public accessor for the shared httpx client."""
        return self._client

    async def generate(self, prompt: str, model: str) -> str:
        """Generate a completion with retry logic.

        Raises:
            ConnectionError: LLM server is unreachable (retried up to LLM_MAX_RETRIES).
            LLMModelError: LLM server returned an HTTP error (e.g. bad request).
                These are NOT retried because the problem is in the request, not
                the connection.
        """
        last_error: ConnectionError | None = None
        for attempt in range(1 + LLM_MAX_RETRIES):
            try:
                result = await self._generate_async(prompt, model)
                if attempt > 0:
                    logger.info("LLM generate succeeded on attempt %d", attempt + 1)
                return result
            except LLMModelError:
                raise  # Model/API errors are not transient — don't retry
            except ConnectionError as exc:
                last_error = exc
                if attempt < LLM_MAX_RETRIES:
                    logger.warning(
                        "LLM generate attempt %d failed, retrying in %.1fs: %s",
                        attempt + 1, LLM_RETRY_DELAY, exc,
                    )
                    await asyncio.sleep(LLM_RETRY_DELAY)
        logger.error("LLM generate failed after %d attempts", 1 + LLM_MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    async def _generate_async(self, prompt: str, model: str) -> str:
        base_url = settings.llm_base_url
        try:
            resp = await self._client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "temperature": settings.llm_temperature,
                    "top_p": settings.llm_top_p,
                    "top_k": settings.llm_top_k,
                    "repeat_penalty": settings.llm_repeat_penalty,
                    "max_tokens": settings.llm_num_predict,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"LLM server unreachable at {base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"LLM request timed out after 120s at {base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMModelError(
                f"LLM server returned HTTP {exc.response.status_code} for model '{model}'",
                status_code=exc.response.status_code,
            ) from exc
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise ConnectionError(
                f"LLM generate response invalid or missing expected key: {exc}"
            ) from exc

    async def generate_stream(
        self, prompt: str, model: str,
    ) -> AsyncGenerator[str]:
        """Stream tokens from llama.cpp's OpenAI-compatible SSE endpoint.

        Yields raw token strings. Raises ConnectionError or LLMModelError
        on failure (same contract as ``generate``).
        """
        base_url = settings.llm_base_url
        try:
            async with self._client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "temperature": settings.llm_temperature,
                    "top_p": settings.llm_top_p,
                    "top_k": settings.llm_top_k,
                    "repeat_penalty": settings.llm_repeat_penalty,
                    "max_tokens": settings.llm_num_predict,
                },
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise LLMModelError(
                        f"LLM server returned HTTP {resp.status_code} for model '{model}'",
                        status_code=resp.status_code,
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"LLM server unreachable at {base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"LLM stream timed out at {base_url}"
            ) from exc
        except LLMModelError:
            raise
        except httpx.HTTPStatusError as exc:
            raise LLMModelError(
                f"LLM server returned HTTP {exc.response.status_code} for model '{model}'",
                status_code=exc.response.status_code,
            ) from exc
