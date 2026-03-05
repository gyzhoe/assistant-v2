"""Shared constants for the AI Helpdesk Assistant backend."""

# ── ChromaDB collection names ────────────────────────────────────────────────

TICKET_COLLECTION = "whd_tickets"
KB_COLLECTION = "kb_articles"
RATED_REPLIES_COLLECTION = "rated_replies"

# ── ChromaDB collection metadata ─────────────────────────────────────────────

COSINE_COLLECTION_META: dict[str, str] = {"hnsw:space": "cosine"}

# ── Chunking defaults ────────────────────────────────────────────────────────

DEFAULT_CHUNK_MAX_TOKENS = 500
DEFAULT_CHUNK_OVERLAP_TOKENS = 50

# ── Ollama retry settings ────────────────────────────────────────────────────

OLLAMA_MAX_RETRIES = 2
OLLAMA_RETRY_DELAY = 1.0


# ── Custom exceptions ───────────────────────────────────────────────────────


class OllamaModelError(RuntimeError):
    """Ollama returned an HTTP error (e.g. model not found, bad request).

    Distinct from ``ConnectionError`` which means Ollama is unreachable.
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
