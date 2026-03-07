"""Shared constants for the AI Helpdesk Assistant backend."""

from __future__ import annotations

from dataclasses import dataclass

# ── GGUF model mapping ──────────────────────────────────────────────────────
# Display name <-> GGUF filename for bundled llama-server models.

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "Qwen3.5-9B-Q4_K_M.gguf": "qwen3.5:9b",
    "Qwen3-14B-Q4_K_M.gguf": "qwen3:14b",
}
"""Map GGUF filename → display name."""

MODEL_GGUF_FILES: dict[str, str] = {v: k for k, v in MODEL_DISPLAY_NAMES.items()}
"""Map display name → GGUF filename (reverse of MODEL_DISPLAY_NAMES)."""

# Embed model filenames to exclude from LLM model listings.
EMBED_MODEL_PREFIXES: tuple[str, ...] = ("nomic-embed-text",)


@dataclass(frozen=True)
class GGUFModelInfo:
    """Metadata for a downloadable GGUF model file."""

    name: str
    display_name: str
    url: str
    description: str
    is_embed: bool


GGUF_MODELS: list[GGUFModelInfo] = [
    GGUFModelInfo(
        name="nomic-embed-text-v1.5.f16.gguf",
        display_name="nomic-embed-text",
        url="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.f16.gguf",
        description="~262 MB",
        is_embed=True,
    ),
    GGUFModelInfo(
        name="Qwen3.5-9B-Q4_K_M.gguf",
        display_name="qwen3.5:9b",
        url="https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf",
        description="~5.3 GB",
        is_embed=False,
    ),
    GGUFModelInfo(
        name="Qwen3-14B-Q4_K_M.gguf",
        display_name="qwen3:14b",
        url="https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf",
        description="~9 GB (optional, better language control)",
        is_embed=False,
    ),
]
"""All known GGUF models with download URLs."""

GGUF_MODELS_BY_NAME: dict[str, GGUFModelInfo] = {m.name: m for m in GGUF_MODELS}
"""Lookup GGUF model info by filename."""

# ── ChromaDB collection names ────────────────────────────────────────────────

TICKET_COLLECTION = "whd_tickets"
KB_COLLECTION = "kb_articles"
RATED_REPLIES_COLLECTION = "rated_replies"

# ── ChromaDB collection metadata ─────────────────────────────────────────────

COSINE_COLLECTION_META: dict[str, str] = {"hnsw:space": "cosine"}

# ── Chunking defaults ────────────────────────────────────────────────────────

DEFAULT_CHUNK_MAX_TOKENS = 500
DEFAULT_CHUNK_OVERLAP_TOKENS = 50

# ── LLM retry settings ───────────────────────────────────────────────────────

LLM_MAX_RETRIES = 2
LLM_RETRY_DELAY = 1.0


# ── Custom exceptions ───────────────────────────────────────────────────────


class LLMModelError(RuntimeError):
    """LLM server returned an HTTP error (e.g. model not found, bad request).

    Distinct from ``ConnectionError`` which means the server is unreachable.
    Carries the HTTP status code for downstream error-code mapping.
    """

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def distance_to_similarity(distance: float) -> float:
    """Convert ChromaDB cosine distance to a similarity score in [0, 1]."""
    return max(0.0, 1.0 - float(distance))


def parse_tags(tags_str: str) -> list[str]:
    """Parse a comma-separated tag string into a list of trimmed, non-empty tags."""
    if not tags_str:
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def serialize_tags(tags: list[str]) -> str:
    """Serialize a list of tags into a comma-separated string for ChromaDB metadata."""
    return ",".join(tags)
