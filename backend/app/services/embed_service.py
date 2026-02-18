import asyncio

import httpx

from app.config import settings


class EmbedService:
    """Generates embeddings using nomic-embed-text via Ollama."""

    def __init__(self, model: str = "nomic-embed-text") -> None:
        self.model = model
        self.base_url = settings.ollama_base_url

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for the given text."""
        return await asyncio.to_thread(self._embed_sync, text)

    def _embed_sync(self, text: str) -> list[float]:
        with httpx.Client() as client:
            resp = client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
