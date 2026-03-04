"""Shared state and helpers for ingest/kb routers."""

import asyncio

from fastapi import HTTPException, Request

# Module-level semaphore: only one ingestion at a time
upload_semaphore = asyncio.Semaphore(1)


def get_client_ip(request: Request) -> str:
    """Extract client IP from a FastAPI request."""
    return request.client.host if request.client else ""


def require_ingestion_available() -> None:
    """Raise 409 if another ingestion is already in progress."""
    if upload_semaphore.locked():
        raise HTTPException(
            status_code=409,
            detail="Another ingestion is already in progress. Please wait.",
        )
