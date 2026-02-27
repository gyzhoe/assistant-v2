"""
URL content loader — fetches web pages, extracts text, and chunks for ingestion.

Includes SSRF prevention to block requests to private/internal networks.
Every redirect hop is re-validated to prevent redirect-based SSRF bypass.
"""

import hashlib
import ipaddress
import logging
import socket
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.utils.chunker import chunk_by_tokens

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"text/html", "text/plain", "application/xhtml+xml"}
ALLOWED_SCHEMES = {"http", "https"}

# Private/reserved IP ranges that must be blocked (SSRF prevention)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    # IPv6
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]


class SSRFError(ValueError):
    """Raised when a URL targets a private/internal network."""


class ContentTypeError(ValueError):
    """Raised when the response Content-Type is not allowed."""


class ResponseTooLargeError(ValueError):
    """Raised when the response body exceeds the size limit."""


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address falls within any blocked network range.

    Also checks IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1) by
    extracting the embedded IPv4 address and testing it separately.
    """
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True

    # IPv4-mapped IPv6 addresses (::ffff:x.x.x.x) bypass IPv4 range checks
    # because the IPv6 address won't match IPv4 networks directly.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        for network in _BLOCKED_NETWORKS:
            if ip.ipv4_mapped in network:
                return True

    return False


def validate_url(url: str) -> str:
    """Validate URL scheme and resolve hostname to check for private IPs.

    Returns the validated URL string.
    Raises SSRFError if the URL targets a private/internal network.
    Raises ValueError if the URL is malformed.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme!r}")

    if not parsed.hostname:
        raise ValueError("URL must include a hostname")

    # Resolve hostname to IP addresses
    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if _is_private_ip(ip):
            raise SSRFError(
                "URL resolves to a private/internal network address. "
                "Requests to internal networks are blocked for security."
            )

    return url


def fetch_url(url: str) -> tuple[str, str, str]:
    """Fetch URL content with security constraints.

    Redirects are followed manually so each hop is re-validated for SSRF.
    Returns (content, content_type, final_url).
    Raises SSRFError, ContentTypeError, ResponseTooLargeError, or httpx errors.
    """
    current_url = url

    with httpx.Client(
        follow_redirects=False,
        timeout=REQUEST_TIMEOUT,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            resp = client.get(current_url, headers={"Accept": "text/html, text/plain"})

            if resp.is_redirect:
                location = resp.headers.get("location", "")
                if not location:
                    raise ValueError("Redirect with no Location header")
                redirect_url = str(resp.url.join(location))
                validate_url(redirect_url)
                current_url = redirect_url
                continue

            resp.raise_for_status()

            # Check content type
            content_type = resp.headers.get("content-type", "")
            mime = content_type.split(";")[0].strip().lower()
            if mime not in ALLOWED_CONTENT_TYPES:
                raise ContentTypeError(
                    f"Content-Type {mime!r} is not supported. "
                    f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
                )

            # Check size
            if len(resp.content) > MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError(
                    f"Response body ({len(resp.content)} bytes) exceeds "
                    f"maximum of {MAX_RESPONSE_BYTES} bytes."
                )

            return resp.text, mime, str(resp.url)

        raise ValueError(f"Too many redirects (max {MAX_REDIRECTS})")


def extract_content(html: str) -> tuple[str, str]:
    """Extract readable text and title from HTML.

    Returns (text, title).
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


def _content_id(content: str) -> str:
    """Stable SHA-256 document ID."""
    return hashlib.sha256(content.encode()).hexdigest()


def load_url(url: str) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Fetch URL, extract content, chunk, and yield (doc_id, text, metadata) tuples.

    Raises SSRFError, ContentTypeError, ResponseTooLargeError, or ValueError.
    """
    validated_url = validate_url(url)
    content, content_type, final_url = fetch_url(validated_url)

    if content_type == "text/plain":
        text = content
        title = urlparse(final_url).path.split("/")[-1] or final_url
    else:
        text, title = extract_content(content)

    if not title:
        title = final_url

    if not text.strip():
        return

    article_id = _content_id(final_url)
    imported_at = datetime.now(UTC).isoformat()

    for chunk in chunk_by_tokens(text, max_tokens=500, overlap_tokens=50):
        if not chunk.strip():
            continue
        doc_id = _content_id(chunk)
        metadata: dict[str, str] = {
            "article_id": article_id,
            "title": title,
            "source_url": final_url,
            "source_type": "url",
            "imported_at": imported_at,
        }
        yield doc_id, chunk, metadata
