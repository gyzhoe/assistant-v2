import asyncio
import logging
import time
from typing import Any, cast

from chromadb.api import ClientAPI
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.request_models import GenerateRequest
from app.models.response_models import ContextDoc, GenerateResponse
from app.routers.feedback import RATED_REPLIES_COLLECTION
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.rag_service import RAGService
from ingestion.pipeline import KB_COLLECTION

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
    start = time.perf_counter()

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
                    category=body.category,
                ),
                ms_docs.search(web_search_keywords),
            )
        else:
            context_docs = await rag.retrieve(
                query=query or "general helpdesk inquiry",
                max_docs=body.max_context_docs,
                category=body.category,
            )
            web_docs = []
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "error_code": "OLLAMA_DOWN",
            },
        ) from exc

    # Fetch pinned articles and prepend to context
    if body.pinned_article_ids:
        pinned_docs = await _fetch_pinned_articles(
            chroma_client, body.pinned_article_ids,
        )
        # Prepend pinned docs before RAG results
        context_docs = pinned_docs + context_docs

    # Build prompt
    context_text = "\n\n---\n\n".join(
        _format_context_doc(doc) for doc in context_docs
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

    # Retrieve dynamic few-shot examples from rated replies
    few_shot_examples = await _get_dynamic_examples(
        chroma_client, query, body.category,
    )

    prompt = _build_prompt(body, context_text, few_shot_examples)
    if body.prompt_suffix.strip():
        prompt += f"\n\nAdditional instructions: {body.prompt_suffix.strip()}"

    # Generate
    try:
        reply = await llm.generate(prompt=prompt, model=body.model)
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(exc),
                "error_code": "OLLAMA_DOWN",
            },
        ) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
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


_MIN_FEWSHOT_SIMILARITY = 0.65


async def _get_dynamic_examples(
    chroma_client: ClientAPI,
    query: str,
    category: str,
) -> list[dict[str, str]]:
    """Retrieve good-rated replies from ChromaDB for dynamic few-shot prompting.

    Returns a list of dicts with 'ticket_subject' and 'reply' keys (max 2).
    Falls back to empty list on any error (collection missing, empty, etc.).
    """
    try:
        embed_svc = EmbedService()
        col = await asyncio.to_thread(
            chroma_client.get_collection, RATED_REPLIES_COLLECTION,
        )
        count = await asyncio.to_thread(col.count)
        if count == 0:
            return []

        embedding = await embed_svc.embed(query)
        n_results = min(2, count)

        results = await asyncio.to_thread(
            _query_rated_sync, col, embedding, n_results, category,
        )

        examples: list[dict[str, str]] = []
        documents: list[str] = results.get("documents", [[]])[0]
        for i, (meta, distance) in enumerate(zip(
            results["metadatas"][0],
            results["distances"][0],
        )):
            score = max(0.0, 1.0 - float(distance))
            if score >= _MIN_FEWSHOT_SIMILARITY:
                # Prefer explicit metadata; fall back to document text for older entries
                subject = str(meta.get("ticket_subject", ""))
                if not subject:
                    doc_text = documents[i] if i < len(documents) else ""
                    subject = doc_text.split("\n", 1)[0] if doc_text else ""
                reply = str(meta.get("reply", ""))
                if reply:
                    examples.append({
                        "ticket_subject": subject,
                        "reply": reply,
                    })

        logger.info("Dynamic few-shot: %d examples found", len(examples))
        return examples

    except Exception:
        logger.debug("Dynamic few-shot retrieval failed — using hardcoded", exc_info=True)
        return []


def _query_rated_sync(
    col: Any,
    embedding: list[float],
    n_results: int,
    category: str,
) -> dict[str, list[list[Any]]]:
    """Synchronous helper for querying rated_replies (runs in to_thread).

    Uses ``Any`` for col and return because ChromaDB's typed stubs
    (Collection.query, QueryResult) are too restrictive for the dynamic
    where-filter and include patterns used here.
    """
    include = ["documents", "metadatas", "distances"]
    if category:
        results: dict[str, list[list[Any]]] = col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=include,
            where={
                "$and": [
                    {"rating": {"$eq": "good"}},
                    {"category": {"$eq": category}},
                ],
            },
        )
        if results["metadatas"][0]:
            return results

    return col.query(  # type: ignore[no-any-return]
        query_embeddings=[embedding],
        n_results=n_results,
        include=include,
        where={"rating": {"$eq": "good"}},
    )


def _relevance_label(score: float) -> str:
    """Map a similarity score to a human-readable relevance label."""
    if score >= 0.75:
        return "HIGH relevance"
    if score >= 0.50:
        return "MODERATE relevance"
    return "LOW relevance"


def _format_context_doc(doc: ContextDoc) -> str:
    """Format a context doc for the prompt, using PINNED label for pinned articles."""
    if doc.metadata.get("source_type") == "pinned":
        return f"[{doc.source.upper()} | PINNED | score: {doc.score:.2f}]\n{doc.content}"
    return (
        f"[{doc.source.upper()} | {_relevance_label(doc.score)} "
        f"| score: {doc.score:.2f}]\n{doc.content}"
    )


async def _fetch_pinned_articles(
    chroma_client: ClientAPI, article_ids: list[str],
) -> list[ContextDoc]:
    """Fetch the first chunk of each pinned article from ChromaDB."""
    try:
        col = await asyncio.to_thread(
            chroma_client.get_collection, KB_COLLECTION,
        )
    except Exception:
        logger.warning(
            "KB collection '%s' not found — skipping pinned articles %s",
            KB_COLLECTION, article_ids, exc_info=True,
        )
        return []

    # Fetch one chunk per article — limit=1 avoids non-deterministic chunk
    # selection since ChromaDB returns chunks in undefined order and there
    # is no chunk_index metadata to sort by.
    pinned: list[ContextDoc] = []
    for aid in article_ids:
        where_filter: dict[str, Any] = {"article_id": {"$eq": aid}}
        try:
            result = await asyncio.to_thread(
                col.get,
                where=where_filter,
                limit=1,
                include=["documents", "metadatas"],
            )
        except Exception:
            logger.warning(
                "Failed to fetch pinned article '%s' from ChromaDB",
                aid, exc_info=True,
            )
            continue

        docs = cast(list[str], result.get("documents") or [])
        metas = cast(list[dict[str, Any]], result.get("metadatas") or [])
        if docs and metas:
            pinned.append(ContextDoc(
                content=docs[0],
                source="kb",
                score=1.0,
                metadata={**metas[0], "source_type": "pinned"},
            ))

    return pinned


_HARDCODED_EXAMPLES = """EXAMPLES

Example 1 (KB match available):
Ticket: "VPN disconnects every 10 minutes"
KB: [HIGH relevance] "VPN timeout is caused by stale credentials. Fix: open Credential Manager > Windows Credentials > remove VPN entries > reconnect."
Reply:
Hi Alex,

1. Press Windows+R, type "control keymgr.dll", press Enter.
2. Under Windows Credentials, delete any entries related to VPN.
3. Reconnect to VPN.

If it still disconnects after clearing credentials, let us know and we'll check your VPN profile server-side.

— IT Support

Example 2 (no KB match):
Ticket: "Outlook keeps crashing on startup"
KB: (no matching articles found)
Reply:
Hi Sarah,

1. Open Outlook in safe mode: press Windows+R, type "outlook /safe", press Enter.
2. If it opens, go to File > Options > Add-ins > Manage COM Add-ins > uncheck all > restart Outlook normally.
3. If safe mode also crashes, open Control Panel > Mail > Show Profiles > create a new profile.

If none of these work, we'll take a closer look at your machine remotely.

— IT Support"""


def _build_examples_section(examples: list[dict[str, str]] | None) -> str:
    """Build the EXAMPLES section using rated replies or hardcoded fallbacks."""
    if not examples:
        return _HARDCODED_EXAMPLES

    parts = ["EXAMPLES"]
    for i, ex in enumerate(examples, 1):
        parts.append(
            f"\nExample {i} (real validated reply for similar ticket):\n"
            f"TICKET: {ex['ticket_subject']}\n"
            f"REPLY: {ex['reply']}"
        )
    return "\n".join(parts)


def _build_prompt(
    body: GenerateRequest,
    context_text: str,
    few_shot_examples: list[dict[str, str]] | None = None,
) -> str:
    subject = body.ticket_subject or "(not available)"
    description = body.ticket_description or "(not available)"
    custom = "\n".join(f"  {k}: {v}" for k, v in body.custom_fields.items()) if body.custom_fields else "(none)"
    examples_section = _build_examples_section(few_shot_examples)
    env_ctx = settings.environment_context.strip()
    environment_section = f"ENVIRONMENT\n{env_ctx}\n\n" if env_ctx else ""
    return f"""You are a first-line IT helpdesk technician drafting a reply to a user's ticket.

TICKET
Subject: {subject}
Requester: {body.requester_name} | Category: {body.category} | Status: {body.status}
Description: {description}
Custom Fields:
{custom}

KNOWLEDGE BASE
{context_text if context_text else "(no matching articles found)"}

{environment_section}GROUNDING RULES
1. ONLY use information from the KNOWLEDGE BASE and ENVIRONMENT sections above. If neither contains a relevant answer, say so and escalate.
2. NEVER invent software versions, URLs, KB article references, ticket numbers, or procedures not present in the context above.
3. If the KNOWLEDGE BASE shows "(no matching articles found)", rely on ENVIRONMENT facts and general IT knowledge only. Do NOT fabricate KB references.
4. Treat TICKET fields as established facts. The Category indicates the connection type (e.g., "NETWORK CONNECTION" = wired Ethernet). Do NOT ask the user to confirm information already in the ticket.
5. Prefer HIGH relevance context over LOW relevance context. Ignore context that does not match the specific problem.

FORMAT RULES
1. Go straight to the action — do NOT repeat or summarize the problem.
2. No apologies, no empathy, no filler ("Thank you for reaching out", "I'm happy to help").
3. Numbered troubleshooting steps. Only ask questions about things NOT already in the ticket.
4. Write for non-technical end users — include exact click paths (e.g., "Open Settings > Network > ...") instead of jargon.
5. Keep it 60-120 words. Greeting by first name, steps, sign-off with just your name.

{examples_section}

REPLY:"""
