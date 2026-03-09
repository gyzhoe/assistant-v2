"""Shared test helpers for setting up app state after create_app()."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService, WebContextDoc
from app.services.model_download_service import ModelDownloadService
from app.services.rag_service import RAGService


def setup_app_state(app: Any) -> None:
    """Set up mock singleton services on app.state.

    Required because create_app() does not run the lifespan, so
    app.state attributes that routers depend on are not initialized.
    """
    mock_llm_client = MagicMock()
    mock_embed_client = MagicMock()
    mock_sync_embed_client = MagicMock()
    mock_http_client = MagicMock()

    if not hasattr(app.state, "chroma_client"):
        app.state.chroma_client = MagicMock()
    if not hasattr(app.state, "current_llm_model"):
        app.state.current_llm_model = "qwen3.5:9b"

    app.state.llm_service = LLMService(client=mock_llm_client)
    embed_svc = EmbedService(client=mock_embed_client)
    embed_svc.embed = AsyncMock(return_value=[0.1] * 768)
    app.state.embed_service = embed_svc
    app.state.sync_embed_service = EmbedService(client=mock_sync_embed_client)
    app.state.ms_docs_service = MicrosoftDocsService(client=mock_http_client)
    app.state.rag_service = RAGService(
        chroma_client=app.state.chroma_client,
        embed_svc=app.state.embed_service,
    )
    app.state.model_download_service = ModelDownloadService()


def create_mock_services() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create a standard set of mock services for test app setup.

    Returns (mock_rag, mock_llm, mock_ms_docs) with sensible defaults:
    - mock_rag.retrieve returns []
    - mock_llm.generate returns "Reply."
    - mock_ms_docs.search returns []
    """
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[])
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="Reply.")
    mock_ms = MagicMock()
    mock_ms.search = AsyncMock(return_value=[])
    return mock_rag, mock_llm, mock_ms


def mock_ms_docs(
    return_value: list[WebContextDoc] | None = None,
) -> MagicMock:
    """Create a mock MicrosoftDocsService instance."""
    mock_instance = MagicMock()
    mock_instance.search = AsyncMock(return_value=return_value or [])
    return mock_instance


def apply_services(
    app: Any,
    mock_rag: MagicMock,
    mock_llm: MagicMock,
    mock_ms: MagicMock,
) -> None:
    """Apply mock services to app.state in one call."""
    app.state.rag_service = mock_rag
    app.state.llm_service = mock_llm
    app.state.ms_docs_service = mock_ms


# --- Shared netstat output samples for port-listening tests ---

NETSTAT_SAMPLE_HEALTH = """\
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1104
  TCP    127.0.0.1:11435        0.0.0.0:0              LISTENING       5432
  TCP    0.0.0.0:49664          0.0.0.0:0              LISTENING       788
"""

NETSTAT_SAMPLE_NATIVE = """\
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1104
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       5432
  TCP    127.0.0.1:8765         127.0.0.1:54321        ESTABLISHED     5432
  TCP    0.0.0.0:49664          0.0.0.0:0              LISTENING       788
"""

NETSTAT_MULTI_PID = """\
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       5432
  TCP    0.0.0.0:8765           0.0.0.0:0              LISTENING       9999
"""
