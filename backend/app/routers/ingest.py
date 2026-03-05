"""
Ingest router — upload files for RAG ingestion and manage collections.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path, PurePosixPath

import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.config import settings
from app.constants import COSINE_COLLECTION_META, KB_COLLECTION, TICKET_COLLECTION, OllamaModelError
from app.models.request_models import IngestUrlRequest
from app.models.response_models import IngestUploadResponse, IngestUrlResponse
from app.routers.kb import invalidate_article_cache
from app.routers.shared import get_client_ip, require_ingestion_available, upload_semaphore
from app.services.audit import audit_log
from ingestion.pipeline import IngestionPipeline
from ingestion.url_loader import (
    ContentTypeError,
    ResponseTooLargeError,
    SSRFError,
    load_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])

ALLOWED_EXTENSIONS = {".json", ".csv", ".html", ".htm", ".pdf"}
ALLOWED_COLLECTIONS = {TICKET_COLLECTION, KB_COLLECTION}
_CHUNK_SIZE = 8192  # 8 KB read chunks for streaming upload


@router.post("/ingest/upload", response_model=IngestUploadResponse)
async def upload_file(request: Request, file: UploadFile) -> IngestUploadResponse:
    """Upload a single file for ingestion into ChromaDB."""
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=422, detail="No filename provided.")

    # Sanitize filename (strip directory components)
    safe_name = PurePosixPath(file.filename).name
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    require_ingestion_available()

    async with upload_semaphore:
        tmp_path: Path | None = None
        try:
            start = time.perf_counter()

            # Stream to temp file with size check
            tmp_path = await _stream_to_temp(file, safe_name, suffix)

            # Check for empty file
            if tmp_path.stat().st_size == 0:
                raise HTTPException(
                    status_code=422,
                    detail="Uploaded file is empty (0 bytes).",
                )

            # Run ingestion in thread pool
            chroma_client = request.app.state.chroma_client
            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            collection_name, chunks = await asyncio.to_thread(
                pipeline.ingest_file, tmp_path,
            )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            invalidate_article_cache()

            warning: str | None = None
            if chunks == 0:
                warning = (
                    "No text content extracted — file may be empty "
                    "or contain only images"
                )

            return IngestUploadResponse(
                filename=safe_name,
                collection=collection_name,
                chunks_ingested=chunks,
                processing_time_ms=elapsed_ms,
                warning=warning,
            )

        except _PayloadTooLargeError as exc:
            raise HTTPException(
                status_code=413,
                detail={"message": str(exc), "error_code": "PAYLOAD_TOO_LARGE"},
            ) from exc
        except OllamaModelError as exc:
            logger.error("Ollama model error during ingestion: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "error_code": "MODEL_ERROR"},
            ) from exc
        except ConnectionError as exc:
            logger.error("Ollama unavailable during ingestion: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding service (Ollama) is unavailable.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during file upload")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during ingestion.",
            ) from exc
        finally:
            if tmp_path is not None:
                await _cleanup_temp(tmp_path)


@router.post("/ingest/collections/{name}/clear")
async def clear_collection(request: Request, name: str) -> dict[str, str]:
    """Delete all documents from a collection."""
    if name not in ALLOWED_COLLECTIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown collection: {name}. "
                f"Allowed: {', '.join(sorted(ALLOWED_COLLECTIONS))}"
            ),
        )

    chroma_client = request.app.state.chroma_client

    try:
        await asyncio.to_thread(chroma_client.delete_collection, name)
    except ValueError:
        # Collection doesn't exist — that's fine, idempotent
        pass

    invalidate_article_cache()

    audit_log("collection_clear", client_ip=get_client_ip(request), detail=f"collection={name}")

    return {"status": "ok", "collection": name}


@router.post("/ingest/url", response_model=IngestUrlResponse)
async def ingest_url(
    request: Request, body: IngestUrlRequest,
) -> IngestUrlResponse:
    """Fetch a URL, extract content, and ingest into ChromaDB."""
    url_str = str(body.url)

    require_ingestion_available()

    async with upload_semaphore:
        try:
            start = time.perf_counter()

            # Validate + fetch + extract + chunk in thread pool
            chunks_list = await asyncio.to_thread(lambda: list(load_url(url_str)))

            if not chunks_list:
                return IngestUrlResponse(
                    url=url_str,
                    collection=KB_COLLECTION,
                    chunks_ingested=0,
                    processing_time_ms=int((time.perf_counter() - start) * 1000),
                    warning="No text content extracted from URL.",
                )

            # Get title from first chunk metadata
            title = chunks_list[0][2].get("title")

            # Run ingestion pipeline
            chroma_client = request.app.state.chroma_client
            embed_service = request.app.state.sync_embed_service
            pipeline = IngestionPipeline(
                chroma_client=chroma_client,
                embed_fn=embed_service.embed_fn,
            )

            col = await asyncio.to_thread(
                chroma_client.get_or_create_collection,
                KB_COLLECTION,
                metadata=COSINE_COLLECTION_META,
            )

            total = await asyncio.to_thread(
                pipeline.upsert_stream, col, iter(chunks_list),
            )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            invalidate_article_cache()

            warning: str | None = None
            if total == 0:
                warning = "No text content extracted from URL."

            return IngestUrlResponse(
                url=url_str,
                collection=KB_COLLECTION,
                chunks_ingested=total,
                processing_time_ms=elapsed_ms,
                title=title,
                warning=warning,
            )

        except SSRFError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ContentTypeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ResponseTooLargeError as exc:
            raise HTTPException(
                status_code=413,
                detail={"message": str(exc), "error_code": "PAYLOAD_TOO_LARGE"},
            ) from exc
        except OllamaModelError as exc:
            logger.error("Ollama model error during URL ingestion: %s", exc)
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "error_code": "MODEL_ERROR"},
            ) from exc
        except ConnectionError as exc:
            logger.error("Ollama unavailable during URL ingestion: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Embedding service (Ollama) is unavailable.",
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"Failed to fetch URL: {exc}",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during URL ingestion")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during URL ingestion.",
            ) from exc


async def _stream_to_temp(
    file: UploadFile, safe_name: str, suffix: str,
) -> Path:
    """Stream uploaded file to a temp file, enforcing size limit."""
    max_bytes = settings.max_upload_bytes
    written = 0

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix, prefix=f"ingest_{safe_name}_",
    )
    tmp_path = Path(tmp.name)

    try:
        while True:
            chunk = await file.read(_CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                tmp.close()
                await _cleanup_temp(tmp_path)
                raise _PayloadTooLargeError(max_bytes)
            tmp.write(chunk)
        tmp.close()
    except _PayloadTooLargeError:
        raise
    except Exception:
        tmp.close()
        await _cleanup_temp(tmp_path)
        raise

    return tmp_path


class _PayloadTooLargeError(Exception):
    """Raised when streamed upload exceeds size limit."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"File exceeds maximum upload size of {max_bytes} bytes.")


async def _cleanup_temp(path: Path, retries: int = 3, delay: float = 0.5) -> None:
    """Remove temp file with retries for Windows AV locks."""
    for attempt in range(retries):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
    logger.warning("Could not delete temp file: %s", path)
