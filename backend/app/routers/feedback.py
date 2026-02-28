"""
Feedback router — stores user ratings (good/bad) for generated replies.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Request, Response

from app.models.request_models import FeedbackRequest
from app.services.embed_service import EmbedService

logger = logging.getLogger(__name__)

RATED_REPLIES_COLLECTION = "rated_replies"

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=204, response_class=Response)
async def submit_feedback(body: FeedbackRequest, request: Request) -> Response:
    """Store a rated reply in ChromaDB for future few-shot retrieval."""
    try:
        chroma_client = request.app.state.chroma_client
        embed_svc = EmbedService()

        query_text = f"{body.ticket_subject}\n{body.ticket_description}"
        embedding = await embed_svc.embed(query_text)

        doc_id = f"rated_{uuid4().hex}"
        col = await asyncio.to_thread(
            chroma_client.get_or_create_collection,
            name=RATED_REPLIES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        await asyncio.to_thread(
            col.add,
            ids=[doc_id],
            embeddings=[embedding],
            documents=[query_text],
            metadatas=[{
                "ticket_subject": body.ticket_subject[:500],
                "category": body.category,
                "reply": body.reply[:2000],
                "rating": body.rating,
                "timestamp": datetime.now(UTC).isoformat(),
            }],
        )
        logger.info(
            "Feedback stored: id=%s rating=%s category=%s",
            doc_id, body.rating, body.category[:40],
        )
    except Exception:
        logger.exception("Failed to store feedback — ignoring to not disrupt UX")

    return Response(status_code=204)
