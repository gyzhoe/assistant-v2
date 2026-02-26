import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.models.request_models import GenerateRequest
from app.models.response_models import GenerateResponse
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate_reply(body: GenerateRequest, request: Request) -> GenerateResponse:
    """Retrieve RAG context and generate a helpdesk reply via Ollama."""
    chroma_client = request.app.state.chroma_client
    rag = RAGService(chroma_client=chroma_client)
    llm = LLMService()

    logger.info("Generate request: model=%s subject=%s", body.model, body.ticket_subject[:80])
    start = time.monotonic()

    # Retrieve context
    query = f"{body.ticket_subject}\n\n{body.ticket_description}".strip()
    try:
        context_docs = await rag.retrieve(
            query=query or "general helpdesk inquiry",
            max_docs=body.max_context_docs,
        )
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": str(exc),
                "error_code": "OLLAMA_DOWN",
            },
        ) from exc

    # Build prompt
    context_text = "\n\n---\n\n".join(
        f"[{doc.source.upper()} | score: {doc.score:.2f}]\n{doc.content}"
        for doc in context_docs
    )

    prompt = _build_prompt(body, context_text)
    if body.prompt_suffix.strip():
        prompt += f"\n\nAdditional instructions: {body.prompt_suffix.strip()}"

    # Generate
    try:
        reply = await llm.generate(prompt=prompt, model=body.model)
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": str(exc),
                "error_code": "OLLAMA_DOWN",
            },
        ) from exc

    latency_ms = int((time.monotonic() - start) * 1000)
    logger.info("Generate complete: model=%s latency=%dms docs=%d", body.model, latency_ms, len(context_docs))

    return GenerateResponse(
        reply=reply,
        model_used=body.model,
        context_docs=context_docs,
        latency_ms=latency_ms,
    )


def _build_prompt(body: GenerateRequest, context_text: str) -> str:
    subject = body.ticket_subject or "(not available)"
    description = body.ticket_description or "(not available)"
    return f"""You are a helpful IT helpdesk assistant. Answer the technician's query based on the ticket context and retrieved knowledge below.

TICKET
Subject: {subject}
Requester: {body.requester_name} | Category: {body.category} | Status: {body.status}
Description: {description}

RELEVANT CONTEXT
{context_text if context_text else "No relevant context found in knowledge base."}

INSTRUCTIONS
- Write a professional, empathetic reply to the requester
- Reference specific steps from the knowledge base when available
- Keep the reply concise (under 200 words unless complexity demands more)
- Do not hallucinate software versions or ticket numbers

REPLY:"""
