import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.request_models import GenerateRequest
from app.models.response_models import GenerateResponse
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate_reply(body: GenerateRequest, request: Request) -> GenerateResponse:
    """Retrieve RAG context and generate a helpdesk reply via Ollama."""
    chroma_client = request.app.state.chroma_client
    rag = RAGService(chroma_client=chroma_client)
    llm = LLMService()
    ms_docs = MicrosoftDocsService()

    logger.info("Generate request: model=%s subject=%s", body.model, body.ticket_subject[:80])
    start = time.monotonic()

    # Retrieve context — RAG + optional Microsoft Learn search in parallel
    query = f"{body.ticket_subject}\n\n{body.ticket_description}".strip()
    web_search_keywords = f"{body.ticket_subject} {body.category}".strip()
    include_web = body.include_web_context and settings.microsoft_docs_enabled

    try:
        if include_web:
            context_docs, web_docs = await asyncio.gather(
                rag.retrieve(
                    query=query or "general helpdesk inquiry",
                    max_docs=body.max_context_docs,
                ),
                ms_docs.search(web_search_keywords),
            )
        else:
            context_docs = await rag.retrieve(
                query=query or "general helpdesk inquiry",
                max_docs=body.max_context_docs,
            )
            web_docs = []
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

    if web_docs:
        web_context = "\n\n---\n\n".join(
            f"[WEB | Microsoft Learn]\n{doc.title}\n{doc.content}"
            for doc in web_docs
        )
        if context_text:
            context_text = f"{context_text}\n\n---\n\n{web_context}"
        else:
            context_text = web_context

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
    logger.info(
        "Generate complete: model=%s latency=%dms docs=%d web_docs=%d",
        body.model, latency_ms, len(context_docs), len(web_docs),
    )

    return GenerateResponse(
        reply=reply,
        model_used=body.model,
        context_docs=context_docs,
        latency_ms=latency_ms,
    )


def _build_prompt(body: GenerateRequest, context_text: str) -> str:
    subject = body.ticket_subject or "(not available)"
    description = body.ticket_description or "(not available)"
    custom = "\n".join(f"  {k}: {v}" for k, v in body.custom_fields.items()) if body.custom_fields else "(none)"
    return f"""You are a first-line IT helpdesk technician drafting a reply to a user's ticket.

TICKET
Subject: {subject}
Requester: {body.requester_name} | Category: {body.category} | Status: {body.status}
Description: {description}
Custom Fields:
{custom}

KNOWLEDGE BASE
{context_text if context_text else "(no matching articles)"}

ENVIRONMENT
- Managed university network using 802.1X authentication.
- Managed devices have hostnames matching GBW-*-**** and connect automatically via dot1x.
- Personal devices must self-register for CampusNet. If self-registration fails, local IT (our department) registers the device manually.
- Internal resources require wired or VPN connection — guest/CampusNet Wi-Fi has limited access.

RULES
1. Treat the TICKET fields as established facts. The Category tells you the connection type (e.g., "NETWORK CONNECTION" = wired Ethernet). Do NOT ask the user to confirm information already provided in the ticket.
2. Focus ONLY on the specific problem described. Ignore KB steps that do not match.
3. Do NOT repeat or summarize the problem back to the user. Go straight to the action.
4. No apologies, no empathy, no filler ("Thank you for reaching out", "I'm happy to help", "We'll do our best"). Be direct and professional.
5. Provide numbered troubleshooting steps the user can try. Only ask questions about things NOT already in the ticket.
6. Write for non-technical end users. If a step is technical (e.g., "check root CA"), either skip it or include the exact click path (e.g., "Open Settings > ..."). Never assume the user knows IT terminology.
7. Keep it short: 50-80 words max. Greeting by first name, steps, sign-off with just your name.
8. Only use KB steps that directly apply. Otherwise use general IT knowledge.
9. Do not invent software versions, ticket numbers, or links.

REPLY:"""
