"""Tests for URL content loader — SSRF prevention, fetching, extraction, and chunking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ingestion.url_loader import (
    ContentTypeError,
    ResponseTooLargeError,
    SSRFError,
    extract_content,
    fetch_url,
    load_url,
    validate_url,
)

# ---------------------------------------------------------------------------
# validate_url — SSRF prevention
# ---------------------------------------------------------------------------


def _mock_getaddrinfo(ip: str):
    """Return a mock getaddrinfo result for a given IP."""
    return [(2, 1, 6, "", (ip, 443))]


def test_validate_url_valid_public() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("93.184.216.34")):
        result = validate_url("https://example.com/page")
    assert result == "https://example.com/page"


def test_validate_url_blocks_localhost() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("127.0.0.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://localhost")


def test_validate_url_blocks_private_10() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("10.0.0.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://internal.corp")


def test_validate_url_blocks_private_172() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("172.16.0.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://internal.corp")


def test_validate_url_blocks_private_192() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("192.168.1.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://internal.corp")


def test_validate_url_blocks_link_local() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("169.254.1.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://link-local.test")


def test_validate_url_blocks_ipv6_loopback() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=[(10, 1, 6, "", ("::1", 443, 0, 0))]):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://ipv6-loopback.test")


def test_validate_url_rejects_ftp_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        validate_url("ftp://files.example.com/data")


def test_validate_url_rejects_no_hostname() -> None:
    with pytest.raises(ValueError, match="hostname"):
        validate_url("https://")


def test_validate_url_rejects_unresolvable_hostname() -> None:
    import socket as _socket

    with patch("ingestion.url_loader.socket.getaddrinfo", side_effect=_socket.gaierror("no host")):
        with pytest.raises(ValueError, match="Could not resolve"):
            validate_url("https://nonexistent.invalid")


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------


def test_fetch_url_success() -> None:
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.content = b"<html><body>Hello</body></html>"
    mock_resp.text = "<html><body>Hello</body></html>"
    mock_resp.url = httpx.URL("https://example.com/page")
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("ingestion.url_loader.httpx.Client", return_value=mock_client):
        content, mime, final_url = fetch_url("https://example.com/page")

    assert content == "<html><body>Hello</body></html>"
    assert mime == "text/html"
    assert final_url == "https://example.com/page"


def test_fetch_url_wrong_content_type() -> None:
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("ingestion.url_loader.httpx.Client", return_value=mock_client):
        with pytest.raises(ContentTypeError, match="image/png"):
            fetch_url("https://example.com/image.png")


def test_fetch_url_too_large() -> None:
    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.content = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("ingestion.url_loader.httpx.Client", return_value=mock_client):
        with pytest.raises(ResponseTooLargeError, match="exceeds"):
            fetch_url("https://example.com/huge")


# ---------------------------------------------------------------------------
# extract_content
# ---------------------------------------------------------------------------


def test_extract_content_strips_boilerplate() -> None:
    html = """
    <html>
    <head><title>My Article</title></head>
    <body>
      <nav>Navigation</nav>
      <header>Header stuff</header>
      <main><p>Main content here.</p></main>
      <footer>Footer</footer>
      <script>alert('x')</script>
      <style>.x{color:red}</style>
    </body>
    </html>
    """
    text, title = extract_content(html)
    assert title == "My Article"
    assert "Main content here." in text
    assert "Navigation" not in text
    assert "Header stuff" not in text
    assert "Footer" not in text
    assert "alert" not in text


def test_extract_content_extracts_title() -> None:
    html = "<html><head><title>Test Title</title></head><body><p>Body</p></body></html>"
    text, title = extract_content(html)
    assert title == "Test Title"
    assert "Body" in text


def test_extract_content_no_title() -> None:
    html = "<html><body><p>No title page</p></body></html>"
    text, title = extract_content(html)
    assert title == ""
    assert "No title page" in text


# ---------------------------------------------------------------------------
# load_url — full pipeline
# ---------------------------------------------------------------------------


def test_load_url_yields_chunks() -> None:
    html = "<html><head><title>Test Page</title></head><body><p>Some content for chunking.</p></body></html>"

    with (
        patch("ingestion.url_loader.validate_url", return_value="https://example.com"),
        patch("ingestion.url_loader.fetch_url", return_value=(html, "text/html", "https://example.com")),
    ):
        chunks = list(load_url("https://example.com"))

    assert len(chunks) >= 1
    doc_id, text, metadata = chunks[0]
    assert isinstance(doc_id, str)
    assert len(doc_id) == 64  # SHA-256 hex
    assert "Some content" in text
    assert metadata["source_type"] == "url"
    assert metadata["source_url"] == "https://example.com"
    assert metadata["title"] == "Test Page"


def test_load_url_empty_content_yields_nothing() -> None:
    html = "<html><body></body></html>"

    with (
        patch("ingestion.url_loader.validate_url", return_value="https://example.com"),
        patch("ingestion.url_loader.fetch_url", return_value=(html, "text/html", "https://example.com")),
    ):
        chunks = list(load_url("https://example.com"))

    assert len(chunks) == 0


def test_load_url_plain_text() -> None:
    with (
        patch("ingestion.url_loader.validate_url", return_value="https://example.com/file.txt"),
        patch(
            "ingestion.url_loader.fetch_url",
            return_value=("Plain text content here.", "text/plain", "https://example.com/file.txt"),
        ),
    ):
        chunks = list(load_url("https://example.com/file.txt"))

    assert len(chunks) >= 1
    assert "Plain text content here." in chunks[0][1]
    assert chunks[0][2]["title"] == "file.txt"
