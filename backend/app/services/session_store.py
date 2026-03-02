"""Session store backends — memory and SQLite.

Both backends implement the same async interface:
    create(max_age, client_ip) -> session_id
    validate(session_id) -> bool
    remove(session_id) -> None

Switch via SESSION_BACKEND=memory|sqlite in config.
SQLite backend stores sessions in <chroma_path>/sessions.db so they
survive restarts.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol — both backends implement this
# ---------------------------------------------------------------------------


class SessionBackend(Protocol):
    async def create(self, max_age: int, client_ip: str = "") -> str: ...
    async def validate(self, session_id: str) -> bool: ...
    async def remove(self, session_id: str) -> None: ...


# ---------------------------------------------------------------------------
# In-memory backend (default, backward-compatible)
# ---------------------------------------------------------------------------


@dataclass
class SessionData:
    created_at: float
    expires_at: float
    client_ip: str = ""


@dataclass
class MemorySessionStore:
    """Thread-safe in-memory session store with expiry sweep."""

    _sessions: dict[str, SessionData] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def create(self, max_age: int, client_ip: str = "") -> str:
        """Create a new session and return its ID.  Sweeps expired entries."""
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        async with self._lock:
            self._sweep(now)
            self._sessions[session_id] = SessionData(
                created_at=now,
                expires_at=now + max_age,
                client_ip=client_ip,
            )
        return session_id

    async def validate(self, session_id: str) -> bool:
        """Return True if the session exists and has not expired."""
        now = time.time()
        async with self._lock:
            data = self._sessions.get(session_id)
            if data is None:
                return False
            if now >= data.expires_at:
                del self._sessions[session_id]
                return False
            return True

    async def remove(self, session_id: str) -> None:
        """Delete a session by ID (no-op if missing)."""
        async with self._lock:
            self._sessions.pop(session_id, None)

    def _sweep(self, now: float) -> None:
        """Remove all expired sessions.  Must be called under lock."""
        expired = [
            sid for sid, data in self._sessions.items()
            if now >= data.expires_at
        ]
        for sid in expired:
            del self._sessions[sid]


# ---------------------------------------------------------------------------
# SQLite backend — sessions survive restarts
# ---------------------------------------------------------------------------


class SQLiteSessionStore:
    """SQLite-backed session store.  Sessions persist across restarts.

    The database file is stored alongside ChromaDB data at
    ``<chroma_path>/sessions.db``.  All SQLite operations run in
    ``asyncio.to_thread`` so they never block the event loop.

    An asyncio.Lock serialises writes to prevent concurrent-write issues
    with SQLite (which only supports one writer at a time).
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_dir = Path(settings.chroma_path)
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "sessions.db")
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Open a new connection (SQLite is thread-safe with check_same_thread=False)."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        """Create the sessions table if it doesn't exist."""
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    client_ip  TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_expires "
                "ON sessions (expires_at)"
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("SQLite session store initialized at %s", self._db_path)

    def _create_sync(self, max_age: int, client_ip: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        conn = self._get_conn()
        try:
            # Sweep expired entries
            conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (now,)
            )
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, expires_at, client_ip) "
                "VALUES (?, ?, ?, ?)",
                (session_id, now, now + max_age, client_ip),
            )
            conn.commit()
        finally:
            conn.close()
        return session_id

    def _validate_sync(self, session_id: str) -> bool:
        now = time.time()
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT expires_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            if now >= row[0]:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                return False
            return True
        finally:
            conn.close()

    def _remove_sync(self, session_id: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        finally:
            conn.close()

    async def create(self, max_age: int, client_ip: str = "") -> str:
        async with self._lock:
            return await asyncio.to_thread(
                self._create_sync, max_age, client_ip,
            )

    async def validate(self, session_id: str) -> bool:
        async with self._lock:
            return await asyncio.to_thread(
                self._validate_sync, session_id,
            )

    async def remove(self, session_id: str) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._remove_sync, session_id,
            )


# ---------------------------------------------------------------------------
# Factory — returns the backend configured in settings
# ---------------------------------------------------------------------------


def create_session_store() -> MemorySessionStore | SQLiteSessionStore:
    """Create the session store based on SESSION_BACKEND setting."""
    backend = settings.session_backend
    if backend == "sqlite":
        return SQLiteSessionStore()
    if backend == "memory":
        return MemorySessionStore()
    logger.warning(
        "Unknown SESSION_BACKEND=%r, falling back to memory", backend,
    )
    return MemorySessionStore()
