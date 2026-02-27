import asyncio
import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 1.0


class LLMService:
    """Generates text completions via Ollama."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url

    async def generate(self, prompt: str, model: str) -> str:
        """Generate a completion with retry logic. Raises ConnectionError if Ollama is unreachable."""
        last_error: ConnectionError | None = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                result = await asyncio.to_thread(self._generate_sync, prompt, model)
                if attempt > 0:
                    logger.info("Ollama generate succeeded on attempt %d", attempt + 1)
                return result
            except ConnectionError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Ollama generate attempt %d failed, retrying in %.1fs: %s",
                        attempt + 1, RETRY_DELAY, exc,
                    )
                    await asyncio.sleep(RETRY_DELAY)
        logger.error("Ollama generate failed after %d attempts", 1 + MAX_RETRIES)
        raise last_error  # type: ignore[misc]

    def _generate_sync(self, prompt: str, model: str) -> str:
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
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
                    },
                    timeout=120.0,
                )
                resp.raise_for_status()
                return str(resp.json()["response"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Ollama service unreachable at {self.base_url}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise ConnectionError(
                f"Ollama request timed out after 120s at {self.base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Ollama returned error {exc.response.status_code}"
            ) from exc
        except (json.JSONDecodeError, KeyError) as exc:
            raise ConnectionError(
                f"Ollama generate response invalid or missing 'response' key: {exc}"
            ) from exc
