"""Shared test helpers for setting up app state after create_app()."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.rag_service import RAGService


def setup_app_state(app: Any) -> None:
    """Set up mock singleton services on app.state.

    Required because create_app() does not run the lifespan, so
    app.state attributes that routers depend on are not initialized.
    """
    mock_client = MagicMock()
    mock_sync_client = MagicMock()

    if not hasattr(app.state, "chroma_client"):
        app.state.chroma_client = MagicMock()
    if not hasattr(app.state, "ollama_reachable"):
        app.state.ollama_reachable = False

    app.state.llm_service = LLMService(client=mock_client)
    app.state.embed_service = EmbedService(client=mock_client)
    app.state.sync_embed_service = EmbedService(client=mock_sync_client)
    app.state.ms_docs_service = MicrosoftDocsService(client=mock_client)
    app.state.rag_service = RAGService(
        chroma_client=app.state.chroma_client,
        embed_svc=app.state.embed_service,
    )
