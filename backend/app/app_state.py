"""Typed application state accessor.

Provides a thin typed wrapper over ``app.state`` so that routers
can access singleton services without per-line ``# type: ignore``
or ``cast()`` calls.
"""

from dataclasses import dataclass

from chromadb.api import ClientAPI

from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService
from app.services.microsoft_docs import MicrosoftDocsService
from app.services.model_download_service import ModelDownloadService
from app.services.rag_service import RAGService


@dataclass
class AppState:
    """Typed container for app.state attributes set during lifespan."""

    llm_service: LLMService
    embed_service: EmbedService
    sync_embed_service: EmbedService
    ms_docs_service: MicrosoftDocsService
    rag_service: RAGService
    chroma_client: ClientAPI
    current_llm_model: str
    model_download_service: ModelDownloadService
