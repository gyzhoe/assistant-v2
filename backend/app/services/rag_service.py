import asyncio
from typing import Any

import chromadb

from app.models.response_models import ContextDoc
from app.services.embed_service import EmbedService


class RAGService:
    """Retrieves relevant documents from ChromaDB using semantic search."""

    TICKET_COLLECTION = "whd_tickets"
    KB_COLLECTION = "kb_articles"

    def __init__(self, chroma_client: chromadb.ClientAPI) -> None:
        self.client = chroma_client
        self.embed_svc = EmbedService()

    async def retrieve(self, query: str, max_docs: int = 5) -> list[ContextDoc]:
        """Embed query, search both collections, merge and rank by score."""
        embedding = await self.embed_svc.embed(query)

        ticket_docs, kb_docs = await asyncio.gather(
            self._query_collection(self.TICKET_COLLECTION, embedding, max_docs // 2 + 1),
            self._query_collection(self.KB_COLLECTION, embedding, max_docs - max_docs // 2),
        )

        all_docs = ticket_docs + kb_docs
        all_docs.sort(key=lambda d: d.score, reverse=True)
        return all_docs[:max_docs]

    async def _query_collection(
        self, name: str, embedding: list[float], n_results: int
    ) -> list[ContextDoc]:
        return await asyncio.to_thread(self._query_sync, name, embedding, n_results)

    def _query_sync(
        self, name: str, embedding: list[float], n_results: int
    ) -> list[ContextDoc]:
        try:
            col = self.client.get_collection(name)
        except Exception:
            return []

        count = col.count()
        if count == 0:
            return []

        n_results = min(n_results, count)
        results: Any = col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        docs = []
        for content, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            source = "ticket" if name == self.TICKET_COLLECTION else "kb"
            score = 1.0 - float(distance)
            docs.append(
                ContextDoc(
                    content=content,
                    source=source,
                    score=round(score, 4),
                    metadata=meta or {},
                )
            )
        return docs
