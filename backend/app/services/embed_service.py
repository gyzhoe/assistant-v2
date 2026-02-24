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
        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0,
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
                f"Ollama embed service unreachable at {self.base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ConnectionError(
                f"Ollama embed returned error {exc.response.status_code}"
            ) from exc
