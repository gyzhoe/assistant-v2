"""Tests for the session store backends (memory and SQLite)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.session_store import (
    MemorySessionStore,
    SQLiteSessionStore,
    create_session_store,
)

# ---------------------------------------------------------------------------
# MemorySessionStore
# ---------------------------------------------------------------------------


class TestMemorySessionStore:
    """Tests for the in-memory session backend."""

    @pytest.mark.asyncio
    async def test_create_and_validate(self) -> None:
        store = MemorySessionStore()
        sid = await store.create(max_age=3600, client_ip="127.0.0.1")
        assert isinstance(sid, str)
        assert len(sid) > 20
        assert await store.validate(sid) is True

    @pytest.mark.asyncio
    async def test_validate_nonexistent(self) -> None:
        store = MemorySessionStore()
        assert await store.validate("nonexistent-session") is False

    @pytest.mark.asyncio
    async def test_remove(self) -> None:
        store = MemorySessionStore()
        sid = await store.create(max_age=3600)
        assert await store.validate(sid) is True
        await store.remove(sid)
        assert await store.validate(sid) is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_noop(self) -> None:
        store = MemorySessionStore()
        await store.remove("does-not-exist")  # Should not raise

    @pytest.mark.asyncio
    async def test_expired_session_fails_validation(self) -> None:
        store = MemorySessionStore()
        sid = await store.create(max_age=1)

        # Manually expire
        async with store._lock:
            store._sessions[sid].expires_at = time.time() - 10

        assert await store.validate(sid) is False

    @pytest.mark.asyncio
    async def test_sweep_removes_expired(self) -> None:
        store = MemorySessionStore()
        sid1 = await store.create(max_age=3600)
        sid2 = await store.create(max_age=1)

        # Expire sid2
        async with store._lock:
            store._sessions[sid2].expires_at = time.time() - 10

        # Create a third session — sweep runs during create
        await store.create(max_age=3600)

        assert sid1 in store._sessions
        assert sid2 not in store._sessions

    @pytest.mark.asyncio
    async def test_client_ip_stored(self) -> None:
        store = MemorySessionStore()
        sid = await store.create(max_age=3600, client_ip="192.168.1.1")
        async with store._lock:
            data = store._sessions[sid]
        assert data.client_ip == "192.168.1.1"


# ---------------------------------------------------------------------------
# SQLiteSessionStore
# ---------------------------------------------------------------------------


class TestSQLiteSessionStore:
    """Tests for the SQLite session backend."""

    def _make_store(self, tmp_path: Path) -> SQLiteSessionStore:
        db_path = str(tmp_path / "test_sessions.db")
        return SQLiteSessionStore(db_path=db_path)

    @pytest.mark.asyncio
    async def test_create_and_validate(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        sid = await store.create(max_age=3600, client_ip="127.0.0.1")
        assert isinstance(sid, str)
        assert len(sid) > 20
        assert await store.validate(sid) is True

    @pytest.mark.asyncio
    async def test_validate_nonexistent(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        assert await store.validate("nonexistent-session") is False

    @pytest.mark.asyncio
    async def test_remove(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        sid = await store.create(max_age=3600)
        assert await store.validate(sid) is True
        await store.remove(sid)
        assert await store.validate(sid) is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        await store.remove("does-not-exist")  # Should not raise

    @pytest.mark.asyncio
    async def test_expired_session_fails_validation(
        self, tmp_path: Path,
    ) -> None:
        store = self._make_store(tmp_path)
        sid = await store.create(max_age=1, client_ip="10.0.0.1")

        # Manually expire via direct SQL
        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "test_sessions.db"))
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (time.time() - 10, sid),
        )
        conn.commit()
        conn.close()

        assert await store.validate(sid) is False

    @pytest.mark.asyncio
    async def test_sessions_survive_new_instance(
        self, tmp_path: Path,
    ) -> None:
        """Key feature: sessions persist across store restarts."""
        db_path = str(tmp_path / "persistent_sessions.db")
        store1 = SQLiteSessionStore(db_path=db_path)
        sid = await store1.create(max_age=3600, client_ip="10.0.0.1")

        # Create a new store instance pointing to same DB
        store2 = SQLiteSessionStore(db_path=db_path)
        assert await store2.validate(sid) is True

    @pytest.mark.asyncio
    async def test_sweep_on_create(self, tmp_path: Path) -> None:
        """Creating a session should sweep expired entries."""
        store = self._make_store(tmp_path)
        sid_old = await store.create(max_age=1)

        # Manually expire
        import sqlite3

        conn = sqlite3.connect(str(tmp_path / "test_sessions.db"))
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (time.time() - 10, sid_old),
        )
        conn.commit()
        conn.close()

        # Create new session — triggers sweep
        await store.create(max_age=3600)

        # Old session should be gone
        assert await store.validate(sid_old) is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestCreateSessionStore:
    """Tests for create_session_store() factory."""

    def test_memory_backend(self) -> None:
        with patch("app.services.session_store.settings") as mock_s:
            mock_s.session_backend = "memory"
            store = create_session_store()
        assert isinstance(store, MemorySessionStore)

    def test_sqlite_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.services.session_store.settings") as mock_s:
                mock_s.session_backend = "sqlite"
                mock_s.chroma_path = tmp
                store = create_session_store()
            assert isinstance(store, SQLiteSessionStore)

    def test_unknown_backend_falls_back_to_memory(self) -> None:
        with patch("app.services.session_store.settings") as mock_s:
            mock_s.session_backend = "redis"
            store = create_session_store()
        assert isinstance(store, MemorySessionStore)
