"""
Ingestion pipeline — orchestrates loading, embedding, and upserting into ChromaDB.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path

from chromadb import Collection
from chromadb.api import ClientAPI

from app.constants import COSINE_COLLECTION_META, KB_COLLECTION, TICKET_COLLECTION
from ingestion.kb_loader import load_kb_html, load_kb_html_dir, load_kb_pdf, load_kb_pdf_dir
from ingestion.ticket_loader import load_tickets

logger = logging.getLogger(__name__)

# Batch size for upsert calls — keeps memory usage predictable
_BATCH_SIZE = 50

# Supported file extensions mapped to (loader, collection)
_EXTENSION_MAP: dict[str, str] = {
    ".json": TICKET_COLLECTION,
    ".csv": TICKET_COLLECTION,
    ".html": KB_COLLECTION,
    ".htm": KB_COLLECTION,
    ".pdf": KB_COLLECTION,
}


class IngestionPipeline:
    def __init__(
        self,
        chroma_client: ClientAPI,
        embed_fn: Callable[[str], list[float]],
    ) -> None:
        self.client = chroma_client
        self._embed_fn = embed_fn

    # ── Ticket ingestion ─────────────────────────────────────────────────────

    def ingest_tickets(self, path: Path) -> int:
        col = self.client.get_or_create_collection(
            name=TICKET_COLLECTION,
            metadata=COSINE_COLLECTION_META,
        )
        return self._upsert_stream(col, load_tickets(path))

    # ── KB ingestion ─────────────────────────────────────────────────────────

    def ingest_kb_html(self, directory: Path) -> int:
        col = self.client.get_or_create_collection(
            name=KB_COLLECTION,
            metadata=COSINE_COLLECTION_META,
        )
        return self._upsert_stream(col, load_kb_html_dir(directory))

    def ingest_kb_pdf(self, directory: Path) -> int:
        col = self.client.get_or_create_collection(
            name=KB_COLLECTION,
            metadata=COSINE_COLLECTION_META,
        )
        return self._upsert_stream(col, load_kb_pdf_dir(directory))

    # ── Single-file ingestion ─────────────────────────────────────────────

    def ingest_file(self, path: Path) -> tuple[str, int]:
        """Auto-route a single file to the correct collection by extension.

        Returns (collection_name, chunks_ingested).
        Raises ValueError for unsupported extensions.
        """
        suffix = path.suffix.lower()
        collection_name = _EXTENSION_MAP.get(suffix)
        if collection_name is None:
            raise ValueError(
                f"Unsupported file extension: {suffix} "
                f"(supported: {', '.join(sorted(_EXTENSION_MAP))})"
            )

        col = self.client.get_or_create_collection(
            name=collection_name,
            metadata=COSINE_COLLECTION_META,
        )

        if suffix in (".json", ".csv"):
            stream = load_tickets(path)
        elif suffix in (".html", ".htm"):
            stream = load_kb_html(path)
        else:  # .pdf
            stream = load_kb_pdf(path)

        chunks = self._upsert_stream(col, stream)
        return collection_name, chunks

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

    # ── Public API ─────────────────────────────────────────────────────────

    def upsert_stream(
        self,
        col: Collection,
        stream: Iterator[tuple[str, str, dict[str, str]]],
    ) -> int:
        """Embed and upsert a stream of (id, text, metadata) tuples into a collection."""
        return self._upsert_stream(col, stream)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _upsert_stream(
        self,
        col: Collection,
        stream: Iterator[tuple[str, str, dict[str, str]]],
    ) -> int:
        total = 0
        batch_num = 0
        batch_ids: list[str] = []
        batch_docs: list[str] = []
        batch_embeds: list[list[float]] = []
        batch_metas: list[dict[str, str]] = []

        for doc_id, text, metadata in stream:
            embedding = self._do_embed(text)
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
                batch_num += 1
                logger.info("Batch %d upserted — %d chunks so far", batch_num, total)
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
            batch_num += 1
            logger.info("Batch %d upserted — %d chunks total (final)", batch_num, total)

        return total

    def _do_embed(self, text: str) -> list[float]:
        """Embed text using the injected embed_fn."""
        return self._embed_fn(text)
