"""Text chunking utilities for the ingestion pipeline."""

import re


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


def chunk_by_markdown_headings(
    text: str, max_tokens: int = 500, overlap_tokens: int = 50,
) -> list[tuple[str, str]]:
    """Split markdown text by ## / ### headings into (section_title, chunk_text) pairs.

    Content before the first heading becomes an "Introduction" section.
    Oversized sections are sub-split via chunk_by_tokens().
    """
    if not text or not text.strip():
        return []

    # Split on lines starting with ## or ###
    heading_pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)

    sections: list[tuple[str, str]] = []
    last_end = 0
    last_title = "Introduction"

    for match in heading_pattern.finditer(text):
        # Capture content before this heading
        body = text[last_end:match.start()].strip()
        if body:
            sections.append((last_title, body))

        last_title = match.group(2).strip()
        last_end = match.end()

    # Capture remaining content after last heading
    trailing = text[last_end:].strip()
    if trailing:
        sections.append((last_title, trailing))

    # Sub-split oversized sections
    result: list[tuple[str, str]] = []
    for title, body in sections:
        word_count = len(body.split())
        if word_count > max_tokens:
            sub_chunks = chunk_by_tokens(body, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
            for i, chunk in enumerate(sub_chunks, start=1):
                result.append((f"{title} (part {i})", chunk))
        else:
            result.append((title, body))

    return result
