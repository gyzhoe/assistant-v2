"""Text chunking utilities for the ingestion pipeline."""


def chunk_by_tokens(
    text: str, max_tokens: int = 500, overlap_tokens: int = 50
) -> list[str]:
    """
    Simple whitespace-based chunking approximation.
    Splits text into chunks of ~max_tokens words with overlap.
    """
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start = end - overlap_tokens

    return chunks


def chunk_by_paragraphs(text: str, max_tokens: int = 1500) -> list[str]:
    """
    Split text by double newlines (paragraphs).
    Merges short paragraphs; splits oversized ones by tokens.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para.split())
        if para_len > max_tokens:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(chunk_by_tokens(para, max_tokens=max_tokens))
        elif current_len + para_len > max_tokens:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks
