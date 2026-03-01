"""Tests for URL content loader — SSRF prevention, fetching, extraction, and chunking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ingestion.url_loader import (
    ContentTypeError,
    ResponseTooLargeError,
    SSRFError,
    _is_private_ip,
    fetch_url,
    load_url,
    validate_url,
)
from ingestion.utils import extract_html_text

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


def test_validate_url_blocks_ipv6_link_local() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=[(10, 1, 6, "", ("fe80::1", 443, 0, 0))]):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://ipv6-link-local.test")


def test_validate_url_blocks_ipv6_unique_local() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=[(10, 1, 6, "", ("fd00::1", 443, 0, 0))]):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://ipv6-ula.test")


def test_validate_url_blocks_zero_network() -> None:
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("0.0.0.1")):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://zero-net.test")


def test_validate_url_rejects_file_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        validate_url("file:///etc/passwd")


def test_validate_url_rejects_data_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        validate_url("data:text/html,<h1>pwned</h1>")


def test_validate_url_error_does_not_leak_ip() -> None:
    """SSRF error messages must not reveal the internal IP address."""
    with patch("ingestion.url_loader.socket.getaddrinfo", return_value=_mock_getaddrinfo("10.42.0.99")):
        with pytest.raises(SSRFError) as exc_info:
            validate_url("http://internal.corp")
    assert "10.42.0.99" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# _is_private_ip — IPv4-mapped IPv6 bypass prevention
# ---------------------------------------------------------------------------


def test_is_private_ip_blocks_ipv4_mapped_ipv6_loopback() -> None:
    """::ffff:127.0.0.1 must be detected as private (IPv4-mapped IPv6)."""
    import ipaddress as _ipa

    ip = _ipa.ip_address("::ffff:127.0.0.1")
    assert _is_private_ip(ip) is True


def test_is_private_ip_blocks_ipv4_mapped_ipv6_private() -> None:
    """::ffff:10.0.0.1 must be detected as private."""
    import ipaddress as _ipa

    ip = _ipa.ip_address("::ffff:10.0.0.1")
    assert _is_private_ip(ip) is True


def test_is_private_ip_allows_public() -> None:
    import ipaddress as _ipa

    ip = _ipa.ip_address("93.184.216.34")
    assert _is_private_ip(ip) is False


def test_validate_url_blocks_ipv4_mapped_ipv6() -> None:
    """DNS returning ::ffff:127.0.0.1 must be blocked."""
    with patch(
        "ingestion.url_loader.socket.getaddrinfo",
        return_value=[(10, 1, 6, "", ("::ffff:127.0.0.1", 443, 0, 0))],
    ):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_url("http://mapped-ipv6.test")


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------


def _make_mock_response(
    *,
    content_type: str = "text/html; charset=utf-8",
    body: bytes = b"<html><body>Hello</body></html>",
    text: str = "<html><body>Hello</body></html>",
    url: str = "https://example.com/page",
    is_redirect: bool = False,
    status_code: int = 200,
    location: str | None = None,
) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.headers = {"content-type": content_type}
    if location:
        resp.headers["location"] = location
    resp.content = body
    resp.text = text
    resp.url = httpx.URL(url)
    resp.is_redirect = is_redirect
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_url_success() -> None:
    mock_resp = _make_mock_response()

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
    mock_resp = _make_mock_response(content_type="image/png", is_redirect=False)

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("ingestion.url_loader.httpx.Client", return_value=mock_client):
        with pytest.raises(ContentTypeError, match="image/png"):
            fetch_url("https://example.com/image.png")


def test_fetch_url_too_large() -> None:
    big_body = b"x" * (6 * 1024 * 1024)
    mock_resp = _make_mock_response(content_type="text/html", body=big_body, is_redirect=False)

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("ingestion.url_loader.httpx.Client", return_value=mock_client):
        with pytest.raises(ResponseTooLargeError, match="exceeds"):
            fetch_url("https://example.com/huge")


def test_fetch_url_follows_safe_redirect() -> None:
    """Redirects to public IPs should be followed normally."""
    redirect_resp = _make_mock_response(
        is_redirect=True,
        status_code=302,
        url="https://example.com/old",
        location="https://example.com/new",
    )
    final_resp = _make_mock_response(url="https://example.com/new")

    mock_client = MagicMock()
    mock_client.get.side_effect = [redirect_resp, final_resp]
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("ingestion.url_loader.httpx.Client", return_value=mock_client),
        patch("ingestion.url_loader.validate_url", return_value="https://example.com/new"),
    ):
        content, mime, final_url = fetch_url("https://example.com/old")

    assert final_url == "https://example.com/new"


def test_fetch_url_blocks_redirect_to_private_ip() -> None:
    """Redirect-based SSRF: public URL redirects to internal IP must be blocked."""
    redirect_resp = _make_mock_response(
        is_redirect=True,
        status_code=302,
        url="https://evil.com/redir",
        location="http://169.254.169.254/latest/meta-data/",
    )

    mock_client = MagicMock()
    mock_client.get.return_value = redirect_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("ingestion.url_loader.httpx.Client", return_value=mock_client),
        patch(
            "ingestion.url_loader.validate_url",
            side_effect=SSRFError("URL resolves to a private/internal network address."),
        ),
    ):
        with pytest.raises(SSRFError, match="private/internal"):
            fetch_url("https://evil.com/redir")


def test_fetch_url_blocks_redirect_to_localhost() -> None:
    """Redirect to localhost must be blocked."""
    redirect_resp = _make_mock_response(
        is_redirect=True,
        status_code=301,
        url="https://evil.com/go",
        location="http://127.0.0.1:8765/health",
    )

    mock_client = MagicMock()
    mock_client.get.return_value = redirect_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("ingestion.url_loader.httpx.Client", return_value=mock_client),
        patch(
            "ingestion.url_loader.validate_url",
            side_effect=SSRFError("URL resolves to a private/internal network address."),
        ),
    ):
        with pytest.raises(SSRFError, match="private/internal"):
            fetch_url("https://evil.com/go")


def test_fetch_url_too_many_redirects() -> None:
    """Exceeding MAX_REDIRECTS must raise ValueError."""
    redirect_resp = _make_mock_response(
        is_redirect=True,
        status_code=302,
        url="https://example.com/loop",
        location="https://example.com/loop",
    )

    mock_client = MagicMock()
    mock_client.get.return_value = redirect_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch("ingestion.url_loader.httpx.Client", return_value=mock_client),
        patch("ingestion.url_loader.validate_url", return_value="https://example.com/loop"),
    ):
        with pytest.raises(ValueError, match="Too many redirects"):
            fetch_url("https://example.com/loop")


# ---------------------------------------------------------------------------
# extract_html_text
# ---------------------------------------------------------------------------


def test_extract_html_text_strips_boilerplate() -> None:
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
    text, title = extract_html_text(html)
    assert title == "My Article"
    assert "Main content here." in text
    assert "Navigation" not in text
    assert "Header stuff" not in text
    assert "Footer" not in text
    assert "alert" not in text


def test_extract_html_text_extracts_title() -> None:
    html = "<html><head><title>Test Title</title></head><body><p>Body</p></body></html>"
    text, title = extract_html_text(html)
    assert title == "Test Title"
    assert "Body" in text


def test_extract_html_text_no_title() -> None:
    html = "<html><body><p>No title page</p></body></html>"
    text, title = extract_html_text(html)
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
