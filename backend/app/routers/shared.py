"""Shared state for ingest/kb routers."""

import asyncio

# Module-level semaphore: only one ingestion at a time
upload_semaphore = asyncio.Semaphore(1)
