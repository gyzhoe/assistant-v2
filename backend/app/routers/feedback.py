"""
Feedback router — stores user ratings (good/bad) for generated replies.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.models.request_models import FeedbackRequest
from app.services.embed_service import EmbedService

logger = logging.getLogger(__name__)

RATED_REPLIES_COLLECTION = "rated_replies"

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=200)
async def submit_feedback(body: FeedbackRequest, request: Request) -> JSONResponse:
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
    except (ConnectionError, ConnectionRefusedError, OSError):
        logger.warning("Ollama/ChromaDB unavailable — feedback not stored")
        raise HTTPException(
            status_code=503,
            detail="Embedding service unavailable. Feedback not stored.",
        )

    return JSONResponse(status_code=200, content={"id": doc_id})


_DOC_ID_PATTERN = r"^rated_[a-f0-9]{32}$"


@router.delete("/feedback/{doc_id}", status_code=204)
async def delete_feedback(
    request: Request,
    doc_id: str = Path(pattern=_DOC_ID_PATTERN),
) -> Response:
    """Delete a rated reply from ChromaDB by document ID."""
    try:
        chroma_client = request.app.state.chroma_client
        col = await asyncio.to_thread(
            chroma_client.get_or_create_collection,
            name=RATED_REPLIES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        # Check if the document exists before deleting
        result = await asyncio.to_thread(col.get, ids=[doc_id])
        if not result["ids"]:
            raise HTTPException(status_code=404, detail="Feedback not found")

        await asyncio.to_thread(col.delete, ids=[doc_id])
        logger.info("Feedback deleted: id=%s", doc_id)
    except HTTPException:
        raise
    except (ConnectionError, ConnectionRefusedError, OSError):
        logger.warning("ChromaDB unavailable — feedback not deleted")
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Feedback not deleted.",
        )

    return Response(status_code=204)
