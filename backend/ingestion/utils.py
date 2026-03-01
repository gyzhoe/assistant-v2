"""Shared ingestion utilities."""

import hashlib

from bs4 import BeautifulSoup


def content_id(content: str) -> str:
    """Stable SHA-256 document ID — re-ingesting same content is idempotent."""
    return hashlib.sha256(content.encode()).hexdigest()


def extract_html_text(html: str) -> tuple[str, str]:
    """Extract readable text and title from HTML, stripping boilerplate.

    Returns (text, title). If no title tag is found, title is an empty string.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Remove boilerplate elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find("div", {"role": "main"})
    target = main if main else soup.body if soup.body else soup

    text = target.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines), title
