"""Shared ASGI helpers for middleware modules."""

import json

from starlette.types import Scope, Send


async def send_json_error(send: Send, status: int, body: dict[str, object]) -> None:
    """Send a JSON error response directly via ASGI send."""
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(payload)).encode("ascii")],
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def get_header(scope: Scope, name: bytes) -> str:
    """Extract a single header value from an ASGI scope (case-insensitive key)."""
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def get_client_ip(scope: Scope) -> str:
    """Extract the client IP from an ASGI scope."""
    client: tuple[str, int] | None = scope.get("client")
    if client:
        return client[0]
    return "unknown"
