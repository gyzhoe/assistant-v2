import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, cast

from chromadb.api import ClientAPI
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.constants import KB_COLLECTION, LLMModelError
from app.models.request_models import GenerateRequest
from app.models.response_models import ContextDoc, ErrorCode, GenerateResponse
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.prompt_service import (
    _build_prompt,
    _format_context_doc,
    _get_dynamic_examples,
)
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


async def _prepare_context(
    body: GenerateRequest, request: Request,
) -> tuple[list[ContextDoc], str, int]:
    """Retrieve RAG context, pinned articles, and web docs; build the prompt.

    Returns (context_docs, prompt, web_docs_count).
    """
    chroma_client = request.app.state.chroma_client
    rag: RAGService = request.app.state.rag_service
    ms_docs: MicrosoftDocsService = request.app.state.ms_docs_service

    query = f"{body.ticket_subject}\n\n{body.ticket_description}".strip()
    effective_query = query or "general helpdesk inquiry"
    web_search_keywords = f"{body.ticket_subject} {body.category}".strip()
    include_web = body.include_web_context and settings.microsoft_docs_enabled

    # Embed the query ONCE and reuse for RAG + few-shot retrieval
    embed_svc: EmbedService = request.app.state.embed_service
    embedding = await embed_svc.embed(effective_query)

    if include_web:
        context_docs, web_docs = await asyncio.gather(
            rag.retrieve(
                query=effective_query,
                max_docs=body.max_context_docs,
                category=body.category,
                embedding=embedding,
            ),
            ms_docs.search(web_search_keywords),
        )
    else:
        context_docs = await rag.retrieve(
            query=effective_query,
            max_docs=body.max_context_docs,
            category=body.category,
            embedding=embedding,
        )
        web_docs = []

    # Fetch pinned articles and prepend to context
    if body.pinned_article_ids:
        pinned_docs = await _fetch_pinned_articles(
            chroma_client, body.pinned_article_ids,
        )
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

    few_shot_examples = await _get_dynamic_examples(
        chroma_client, effective_query, body.category, embedding,
    )

    prompt = _build_prompt(body, context_text, few_shot_examples)
    if body.prompt_suffix.strip():
        prompt += (
            "\n\n<user_additional_instructions>"
            f"{body.prompt_suffix.strip()}"
            "</user_additional_instructions>"
        )

    return context_docs, prompt, len(web_docs)


def _sse_event(data: dict[str, object]) -> str:
    """Format a single SSE event line."""
    return f"data: {json.dumps(data)}\n\n"


async def _sse_error_only(exc: Exception) -> AsyncGenerator[str]:
    """Yield a single SSE error event for context-preparation failures."""
    if isinstance(exc, ConnectionError):
        code = ErrorCode.LLM_DOWN.value
    elif isinstance(exc, LLMModelError):
        code = ErrorCode.MODEL_ERROR.value
    else:
        code = ErrorCode.INTERNAL_ERROR.value
    yield _sse_event({"type": "error", "error_code": code, "message": str(exc)})


async def _stream_generate(
    llm: LLMService,
    body: GenerateRequest,
    context_docs: list[ContextDoc],
    prompt: str,
    start: float,
) -> AsyncGenerator[str]:
    """Async generator producing SSE events for the streaming endpoint."""
    # First event: meta with context docs
    yield _sse_event({
        "type": "meta",
        "context_docs": [doc.model_dump() for doc in context_docs],
    })

    try:
        async for token in llm.generate_stream(prompt=prompt, model=body.model):
            yield _sse_event({"type": "token", "content": token})
    except (ConnectionError, LLMModelError) as exc:
        yield _sse_event({
            "type": "error",
            "error_code": ErrorCode.LLM_DOWN.value
            if isinstance(exc, ConnectionError)
            else ErrorCode.MODEL_ERROR.value,
            "message": str(exc),
        })
        return
    except Exception:
        logger.exception("Unexpected error during SSE streaming")
        yield _sse_event({
            "type": "error",
            "error_code": ErrorCode.INTERNAL_ERROR.value,
            "message": "Internal server error",
        })
        return

    latency_ms = int((time.perf_counter() - start) * 1000)
    yield _sse_event({"type": "done", "latency_ms": latency_ms})


@router.post("/generate", response_model=GenerateResponse)
async def generate_reply(
    body: GenerateRequest, request: Request,
) -> GenerateResponse | StreamingResponse:
    """Retrieve RAG context and generate a helpdesk reply via LLM server.

    When ``body.stream`` is True, returns an SSE ``StreamingResponse``.
    Otherwise returns a JSON ``GenerateResponse``.
    """
    llm: LLMService = request.app.state.llm_service

    logger.info(
        "Generate request: model=%s subject_len=%d stream=%s",
        body.model, len(body.ticket_subject), body.stream,
    )
    start = time.perf_counter()

    if body.stream:
        try:
            context_docs, prompt, _web_count = await _prepare_context(
                body, request,
            )
        except (ConnectionError, LLMModelError) as exc:
            return StreamingResponse(
                _sse_error_only(exc),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        return StreamingResponse(
            _stream_generate(llm, body, context_docs, prompt, start),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming JSON response (existing behavior)
    context_docs, prompt, web_count = await _prepare_context(body, request)
    reply = await llm.generate(prompt=prompt, model=body.model)

    latency_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "Generate complete: model=%s latency=%dms docs=%d web_docs=%d",
        body.model, latency_ms, len(context_docs), web_count,
    )

    return GenerateResponse(
        reply=reply,
        model_used=body.model,
        context_docs=context_docs,
        latency_ms=latency_ms,
    )


async def _fetch_pinned_articles(
    chroma_client: ClientAPI, article_ids: list[str],
) -> list[ContextDoc]:
    """Fetch the first chunk of each pinned article from ChromaDB in parallel."""
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

    async def _fetch_one(aid: str) -> ContextDoc | None:
        # Fetch one chunk per article — limit=1 avoids non-deterministic chunk
        # selection since ChromaDB returns chunks in undefined order and there
        # is no chunk_index metadata to sort by.
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
            return None

        docs = cast(list[str], result.get("documents") or [])
        metas = cast(list[dict[str, Any]], result.get("metadatas") or [])
        if docs and metas:
            return ContextDoc(
                content=docs[0],
                source="kb",
                score=1.0,
                metadata={**metas[0], "source_type": "pinned"},
            )
        return None

    results = await asyncio.gather(*(_fetch_one(aid) for aid in article_ids))
    return [doc for doc in results if doc is not None]
