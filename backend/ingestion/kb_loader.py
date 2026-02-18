"""
KB article loader — parses HTML and PDF knowledge base articles.

HTML: splits by <h2>/<h3> headings using BeautifulSoup.
PDF: page-by-page with 500-token sliding window and 50-token overlap.
"""

import hashlib
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

from app.utils.chunker import chunk_by_tokens


def _content_id(content: str) -> str:
    """Stable SHA-256 document ID — re-ingesting same content is idempotent."""
    return hashlib.sha256(content[:200].encode()).hexdigest()


# ── HTML loader ───────────────────────────────────────────────────────────────


def load_kb_html(path: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """
    Yield (doc_id, text, metadata) tuples from an HTML KB article.
    Splits on <h2> and <h3> headings; each section becomes one or more chunks.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Extract article title
    title_tag = soup.find("h1") or soup.find("title")
    article_title = title_tag.get_text(strip=True) if title_tag else path.stem

    # Split by heading tags
    sections: list[tuple[str, str]] = []  # (heading, content)
    current_heading = article_title
    current_parts: list[str] = []

    for element in soup.find_all(["h1", "h2", "h3", "p", "li", "pre"]):
        if isinstance(element, Tag) and element.name in ("h1", "h2", "h3"):
            if current_parts:
                sections.append((current_heading, " ".join(current_parts)))
                current_parts = []
            current_heading = element.get_text(strip=True)
        else:
            text = element.get_text(strip=True)
            if text:
                current_parts.append(text)

    if current_parts:
        sections.append((current_heading, " ".join(current_parts)))

    article_id = _content_id(article_title + path.name)

    for heading, body in sections:
        if not body.strip():
            continue
        for chunk in chunk_by_tokens(body, max_tokens=500, overlap_tokens=50):
            combined = f"{heading}\n\n{chunk}" if heading != article_title else chunk
            doc_id = _content_id(combined)
            metadata: dict[str, str] = {
                "article_id": article_id,
                "title": article_title,
                "section": heading,
                "source_file": path.name,
                "source_type": "html",
            }
            yield doc_id, combined, metadata


def load_kb_html_dir(directory: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Yield chunks from all .html files in a directory (non-recursive)."""
    for html_path in sorted(directory.glob("*.html")):
        try:
            yield from load_kb_html(html_path)
        except Exception as exc:
            # Log and continue — one bad file shouldn't abort the batch
            print(f"[WARN] Skipping {html_path.name}: {exc}")


# ── PDF loader ────────────────────────────────────────────────────────────────


def load_kb_pdf(path: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """
    Yield (doc_id, text, metadata) tuples from a PDF KB article.
    Uses page-by-page extraction with 500-token sliding window, 50-token overlap.
    """
    reader = PdfReader(str(path))
    article_title = path.stem.replace("-", " ").replace("_", " ").title()
    article_id = _content_id(article_title + path.name)

    full_text_parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        full_text_parts.append(page_text)

    full_text = "\n\n".join(full_text_parts)

    for chunk in chunk_by_tokens(full_text, max_tokens=500, overlap_tokens=50):
        if not chunk.strip():
            continue
        doc_id = _content_id(chunk)
        metadata: dict[str, str] = {
            "article_id": article_id,
            "title": article_title,
            "source_file": path.name,
            "source_type": "pdf",
        }
        yield doc_id, chunk, metadata


def load_kb_pdf_dir(directory: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Yield chunks from all .pdf files in a directory (non-recursive)."""
    for pdf_path in sorted(directory.glob("*.pdf")):
        try:
            yield from load_kb_pdf(pdf_path)
        except Exception as exc:
            print(f"[WARN] Skipping {pdf_path.name}: {exc}")
