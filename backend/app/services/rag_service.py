import asyncio
import logging
from typing import Any

from chromadb.api import ClientAPI

from app.config import settings
from app.models.response_models import ContextDoc
from app.services.embed_service import EmbedService

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieves relevant documents from ChromaDB using semantic search."""

    TICKET_COLLECTION = "whd_tickets"
    KB_COLLECTION = "kb_articles"

    def __init__(self, chroma_client: ClientAPI) -> None:
        self.client = chroma_client
        self.embed_svc = EmbedService()

    async def retrieve(
        self, query: str, max_docs: int = 5, category: str = "",
    ) -> list[ContextDoc]:
        """Embed query, search both collections, merge and rank by score.

        If *category* is non-empty, KB retrieval uses a two-phase approach:
        phase 1 queries with a tag filter, phase 2 fills remaining slots
        without a filter (deduplicating against phase 1).
        """
        embedding = await self.embed_svc.embed(query)

        kb_target = max_docs - max_docs // 2  # KB gets slightly more
        ticket_target = max_docs // 2 + 1

        if category:
            # Two-phase: filtered + unfiltered KB
            filtered_target = kb_target // 2 + 1
            ticket_docs, kb_filtered = await asyncio.gather(
                self._query_collection(
                    self.TICKET_COLLECTION, embedding, ticket_target,
                ),
                self._query_collection(
                    self.KB_COLLECTION, embedding, filtered_target,
                    # NOTE: $contains does substring match on the comma-separated
                    # tags string. Category "NET" will also match "NETWORK".
                    # Acceptable for two-phase retrieval since phase 2 backfills
                    # unfiltered results anyway.
                    where={"tags": {"$contains": category}},
                ),
            )

            # Phase 2: fill remaining KB slots with unfiltered results
            remaining = kb_target - len(kb_filtered)
            if remaining > 0:
                kb_unfiltered = await self._query_collection(
                    self.KB_COLLECTION, embedding, remaining + len(kb_filtered),
                )
                # Deduplicate by article_id + content prefix (200 chars
                # to avoid collisions between chunks with similar openings)
                seen_keys = {
                    str(doc.metadata.get("article_id", "")) + doc.content[:200]
                    for doc in kb_filtered
                }
                for doc in kb_unfiltered:
                    key = str(doc.metadata.get("article_id", "")) + doc.content[:200]
                    if key not in seen_keys and len(kb_filtered) < kb_target:
                        kb_filtered.append(doc)
                        seen_keys.add(key)

            all_docs = ticket_docs + kb_filtered
        else:
            ticket_docs, kb_docs = await asyncio.gather(
                self._query_collection(
                    self.TICKET_COLLECTION, embedding, ticket_target,
                ),
                self._query_collection(self.KB_COLLECTION, embedding, kb_target),
            )
            all_docs = ticket_docs + kb_docs

        all_docs.sort(key=lambda d: d.score, reverse=True)

        threshold = settings.rag_min_similarity
        before_count = len(all_docs)
        filtered = [d for d in all_docs if d.score >= threshold]
        if before_count > 0 and len(filtered) < before_count:
            logger.info(
                "RAG filter: %d/%d docs above threshold %.2f",
                len(filtered), before_count, threshold,
            )

        return filtered[:max_docs]

    async def _query_collection(
        self,
        name: str,
        embedding: list[float],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[ContextDoc]:
        return await asyncio.to_thread(
            self._query_sync, name, embedding, n_results, where,
        )

    def _query_sync(
        self,
        name: str,
        embedding: list[float],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[ContextDoc]:
        try:
            col = self.client.get_collection(name)
        except Exception:
            return []

        count = col.count()
        if count == 0:
            return []

        n_results = min(n_results, count)
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_kwargs["where"] = where
        results: Any = col.query(**query_kwargs)

        docs = []
        for content, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            source = "ticket" if name == self.TICKET_COLLECTION else "kb"
            score = max(0.0, 1.0 - float(distance))
            docs.append(
                ContextDoc(
                    content=content,
                    source=source,
                    score=round(score, 4),
                    metadata=meta or {},
                )
            )
        return docs
