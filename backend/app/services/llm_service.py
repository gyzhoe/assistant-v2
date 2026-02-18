import asyncio

import httpx

from app.config import settings


class LLMService:
    """Generates text completions via Ollama."""

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url

    async def generate(self, prompt: str, model: str) -> str:
        """Generate a completion. Raises ConnectionError if Ollama is unreachable."""
        return await asyncio.to_thread(self._generate_sync, prompt, model)

    def _generate_sync(self, prompt: str, model: str) -> str:
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                    timeout=120.0,
                )
                resp.raise_for_status()
                return str(resp.json()["response"])
        except httpx.ConnectError as exc:
            raise ConnectionError(
                f"Ollama service unreachable at {self.base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Ollama returned error {exc.response.status_code}"
            ) from exc
