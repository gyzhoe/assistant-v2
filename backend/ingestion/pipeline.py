"""
Ingestion pipeline — orchestrates loading, embedding, and upserting into ChromaDB.
"""

from collections.abc import Iterator
from pathlib import Path

import httpx
from chromadb import Collection
from chromadb.api import ClientAPI

from app.config import settings
from ingestion.kb_loader import load_kb_html_dir, load_kb_pdf_dir
from ingestion.ticket_loader import load_tickets

TICKET_COLLECTION = "whd_tickets"
KB_COLLECTION = "kb_articles"

# Batch size for upsert calls — keeps memory usage predictable
_BATCH_SIZE = 50


class IngestionPipeline:
    def __init__(self, chroma_client: ClientAPI) -> None:
        self.client = chroma_client

    # ── Ticket ingestion ─────────────────────────────────────────────────────

    def ingest_tickets(self, path: Path) -> int:
        col = self.client.get_or_create_collection(
            name=TICKET_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return self._upsert_stream(col, load_tickets(path))

    # ── KB ingestion ─────────────────────────────────────────────────────────

    def ingest_kb_html(self, directory: Path) -> int:
        col = self.client.get_or_create_collection(
            name=KB_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return self._upsert_stream(col, load_kb_html_dir(directory))

    def ingest_kb_pdf(self, directory: Path) -> int:
        col = self.client.get_or_create_collection(
            name=KB_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        return self._upsert_stream(col, load_kb_pdf_dir(directory))

    # ── Status & management ──────────────────────────────────────────────────

    def status(self) -> dict[str, int]:
        try:
            collections = self.client.list_collections()
            return {col.name: col.count() for col in collections}
        except Exception:
            return {}

    def clear_all(self) -> None:
        for col in self.client.list_collections():
            self.client.delete_collection(col.name)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _upsert_stream(
        self,
        col: Collection,
        stream: Iterator[tuple[str, str, dict[str, str]]],
    ) -> int:
        total = 0
        batch_ids: list[str] = []
        batch_docs: list[str] = []
        batch_embeds: list[list[float]] = []
        batch_metas: list[dict[str, str]] = []

        for doc_id, text, metadata in stream:
            embedding = self._embed(text)
            batch_ids.append(doc_id)
            batch_docs.append(text)
            batch_embeds.append(embedding)
            batch_metas.append(metadata)

            if len(batch_ids) >= _BATCH_SIZE:
                col.upsert(
                    ids=batch_ids,
                    documents=batch_docs,
                    embeddings=batch_embeds,  # type: ignore[arg-type]
                    metadatas=batch_metas,  # type: ignore[arg-type]
                )
                total += len(batch_ids)
                batch_ids, batch_docs, batch_embeds, batch_metas = [], [], [], []

        # Flush remaining
        if batch_ids:
            col.upsert(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=batch_embeds,  # type: ignore[arg-type]
                metadatas=batch_metas,  # type: ignore[arg-type]
            )
            total += len(batch_ids)

        return total

    def _embed(self, text: str) -> list[float]:
        """Embed text using nomic-embed-text via Ollama (synchronous)."""
        with httpx.Client() as client:
            resp = client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=60.0,
            )
            resp.raise_for_status()
            return list(resp.json()["embedding"])
