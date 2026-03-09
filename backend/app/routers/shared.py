"""Shared state and helpers for ingest/kb routers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request

# Module-level semaphore: only one ingestion at a time
upload_semaphore = asyncio.Semaphore(1)


def get_client_ip(request: Request) -> str:
    """Extract client IP from a FastAPI request."""
    return request.client.host if request.client else ""


@asynccontextmanager
async def acquire_ingestion_lock() -> AsyncIterator[None]:
    """Acquire the ingestion semaphore atomically, or raise 409.

    Checks ``locked()`` and acquires in a single atomic step: if the
    semaphore is already held, reject immediately instead of queuing.
    """
    if upload_semaphore.locked():
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Another ingestion is already in progress. Please wait.",
                "error_code": "INGESTION_BUSY",
            },
        )
    await upload_semaphore.acquire()
    try:
        yield
    finally:
        upload_semaphore.release()
