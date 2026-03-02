"""Structured audit logger for security-sensitive admin actions.

Logs to a dedicated ``audit.log`` file with rotation.  Each entry is a
JSON object containing: timestamp, action, client_ip, outcome, and an
optional session_id.

Audited actions: login, logout, session_sweep, article_delete,
collection_clear, shutdown.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_AUDIT_LOG_FILE = Path("audit.log")
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3

_audit_logger: logging.Logger | None = None


def _get_logger() -> logging.Logger:
    """Return (and lazily create) the singleton audit logger."""
    global _audit_logger
    if _audit_logger is not None:
        return _audit_logger

    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # don't duplicate into root/app logs

    handler = RotatingFileHandler(
        _AUDIT_LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    _audit_logger = logger
    return logger


def audit_log(
    action: str,
    *,
    client_ip: str = "",
    outcome: str = "success",
    session_id: str = "",
    detail: str = "",
) -> None:
    """Write a structured JSON audit entry.

    Parameters
    ----------
    action:
        Short action name, e.g. ``login``, ``article_delete``.
    client_ip:
        Remote IP address of the client.
    outcome:
        ``"success"`` or ``"failure"``.
    session_id:
        Session cookie value (if applicable).  Only the first 8
        characters are logged to limit exposure.
    detail:
        Optional free-text detail (e.g. article_id, collection name).
    """
    entry: dict[str, str] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "client_ip": client_ip,
        "outcome": outcome,
    }
    if session_id:
        entry["session_prefix"] = session_id[:8]
    if detail:
        entry["detail"] = detail

    _get_logger().info(json.dumps(entry, separators=(",", ":")))


def reset_audit_logger() -> None:
    """Remove all handlers and reset the singleton — for testing only."""
    global _audit_logger
    if _audit_logger is not None:
        for h in list(_audit_logger.handlers):
            _audit_logger.removeHandler(h)
            h.close()
        _audit_logger = None
