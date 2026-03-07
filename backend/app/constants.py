"""Shared constants for the AI Helpdesk Assistant backend."""

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
