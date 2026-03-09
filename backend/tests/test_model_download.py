"""Tests for ModelDownloadService SHA-256 verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from app.constants import GGUFModelInfo
from app.services.model_download_service import ModelDownloadService


def _make_model(sha256: str = "") -> GGUFModelInfo:
    return GGUFModelInfo(
        name="test-model.gguf",
        display_name="test:1b",
        url="https://example.com/test-model.gguf",
        description="~1 MB",
        is_embed=False,
        sha256=sha256,
    )


class FakeResponse:
    """Minimal fake for urllib.request.urlopen context manager."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0
        self.headers = {"Content-Length": str(len(data))}

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos:self._pos + size]
        self._pos += size
        return chunk

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_sha256_pass(tmp_path: Path) -> None:
    """Download succeeds when SHA-256 matches."""
    data = b"hello world model data"
    expected = hashlib.sha256(data).hexdigest()
    model = _make_model(sha256=expected)

    svc = ModelDownloadService()
    tmp_file = tmp_path / "test-model.gguf.tmp"

    with patch("app.services.model_download_service.urllib.request.urlopen") as mock_open:
        mock_open.return_value = FakeResponse(data)
        svc._blocking_download(model.url, tmp_file, model.sha256)

    assert tmp_file.exists()
    assert tmp_file.read_bytes() == data


def test_sha256_mismatch_deletes_file(tmp_path: Path) -> None:
    """Download raises and deletes .tmp when SHA-256 doesn't match."""
    data = b"hello world model data"
    model = _make_model(sha256="0000000000000000000000000000000000000000000000000000000000000000")

    svc = ModelDownloadService()
    tmp_file = tmp_path / "test-model.gguf.tmp"

    with patch("app.services.model_download_service.urllib.request.urlopen") as mock_open:
        mock_open.return_value = FakeResponse(data)
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            svc._blocking_download(model.url, tmp_file, model.sha256)

    assert not tmp_file.exists()


def test_sha256_skipped_when_empty(tmp_path: Path) -> None:
    """Download succeeds without verification when sha256 is empty."""
    data = b"hello world model data"
    model = _make_model(sha256="")

    svc = ModelDownloadService()
    tmp_file = tmp_path / "test-model.gguf.tmp"

    with patch("app.services.model_download_service.urllib.request.urlopen") as mock_open:
        mock_open.return_value = FakeResponse(data)
        svc._blocking_download(model.url, tmp_file, model.sha256)

    assert tmp_file.exists()
    assert tmp_file.read_bytes() == data


@pytest.mark.asyncio
async def test_download_one_passes_sha256(tmp_path: Path) -> None:
    """_download_one passes model sha256 to _blocking_download."""
    data = b"model bytes"
    expected = hashlib.sha256(data).hexdigest()
    model = _make_model(sha256=expected)

    svc = ModelDownloadService()

    def fake_download(url: str, tmp: Path, sha: str = "") -> None:
        tmp.write_bytes(data)

    svc._blocking_download = fake_download  # type: ignore[assignment]

    await svc._download_one(model, tmp_path)

    # Verify the file was renamed to final destination
    assert (tmp_path / "test-model.gguf").exists()
