import asyncio
import json
import logging

import httpx

from app.config import settings
from app.constants import OLLAMA_MAX_RETRIES, OLLAMA_RETRY_DELAY, OllamaModelError

logger = logging.getLogger(__name__)


class LLMService:
    """Generates text completions via Ollama using a shared async httpx client."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        """Public accessor for the shared httpx client."""
        return self._client

    async def generate(self, prompt: str, model: str) -> str:
        """Generate a completion with retry logic.

        Raises:
            ConnectionError: Ollama is unreachable (retried up to OLLAMA_MAX_RETRIES).
            OllamaModelError: Ollama returned an HTTP error (e.g. model not found).
                These are NOT retried because the problem is in the request, not
                the connection.
        """
        last_error: ConnectionError | None = None
        for attempt in range(1 + OLLAMA_MAX_RETRIES):
            try:
                result = await self._generate_async(prompt, model)
                if attempt > 0:
                    logger.info("Ollama generate succeeded on attempt %d", attempt + 1)
                return result
            except OllamaModelError:
                raise  # Model/API errors are not transient — don't retry
            except ConnectionError as exc:
                last_error = exc
                if attempt < OLLAMA_MAX_RETRIES:
                    logger.warning(
                        "Ollama generate attempt %d failed, retrying in %.1fs: %s",
                        attempt + 1, OLLAMA_RETRY_DELAY, exc,
                    )
                    await asyncio.sleep(OLLAMA_RETRY_DELAY)
        logger.error("Ollama generate failed after %d attempts", 1 + OLLAMA_MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    async def _generate_async(self, prompt: str, model: str) -> str:
        base_url = settings.ollama_base_url
        try:
            resp = await self._client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": settings.llm_temperature,
                        "top_p": settings.llm_top_p,
                        "top_k": settings.llm_top_k,
                        "repeat_penalty": settings.llm_repeat_penalty,
                        "num_predict": settings.llm_num_predict,
                    },
                    "think": False,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["response"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Ollama service unreachable at {base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"Ollama request timed out after 120s at {base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaModelError(
                f"Ollama returned HTTP {exc.response.status_code} for model '{model}'",
                status_code=exc.response.status_code,
            ) from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise ConnectionError(
                f"Ollama generate response invalid or missing 'response' key: {exc}"
            ) from exc
