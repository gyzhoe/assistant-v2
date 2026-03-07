"""Background model download service with progress tracking and cancellation."""

from __future__ import annotations

import asyncio
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.constants import GGUF_MODELS_BY_NAME, GGUFModelInfo

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1 MB


@dataclass
class DownloadState:
    """Mutable snapshot of the current download progress."""

    downloading: bool = False
    current_model: str = ""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    models_completed: int = 0
    models_total: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "downloading": self.downloading,
            "current_model": self.current_model,
            "bytes_downloaded": self.bytes_downloaded,
            "bytes_total": self.bytes_total,
            "models_completed": self.models_completed,
            "models_total": self.models_total,
            "error": self.error,
        }


class ModelDownloadService:
    """Manages background GGUF model downloads with cancellation support."""

    def __init__(self) -> None:
        self._state = DownloadState()
        self._cancel_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def get_status(self) -> dict[str, object]:
        return self._state.to_dict()

    def start_download(
        self,
        model_names: list[str],
        models_dir: Path,
    ) -> dict[str, object]:
        """Start downloading the given models in the background.

        Returns a dict with status and list of models queued.
        """
        if self._state.downloading:
            return {"status": "already_downloading"}

        # Resolve model info objects
        models: list[GGUFModelInfo] = []
        for name in model_names:
            info = GGUF_MODELS_BY_NAME.get(name)
            if info is None:
                return {"status": "error", "error": f"Unknown model: {name}"}
            models.append(info)

        # Reset state
        self._cancel_event.clear()
        self._state = DownloadState(
            downloading=True,
            models_total=len(models),
        )

        self._task = asyncio.create_task(
            self._download_all(models, models_dir),
        )
        return {"status": "started", "models": [m.name for m in models]}

    def cancel(self) -> dict[str, str]:
        if not self._state.downloading:
            return {"status": "not_downloading"}
        self._cancel_event.set()
        return {"status": "cancelling"}

    async def _download_all(
        self,
        models: list[GGUFModelInfo],
        models_dir: Path,
    ) -> None:
        models_dir.mkdir(parents=True, exist_ok=True)
        try:
            for model in models:
                if self._cancel_event.is_set():
                    logger.info("Download cancelled before %s", model.name)
                    break
                self._state.current_model = model.name
                self._state.bytes_downloaded = 0
                self._state.bytes_total = 0
                await self._download_one(model, models_dir)
                self._state.models_completed += 1
        except Exception as exc:
            logger.error("Download failed: %s", exc)
            self._state.error = str(exc)
        finally:
            self._state.downloading = False
            self._state.current_model = ""

    async def _download_one(
        self,
        model: GGUFModelInfo,
        models_dir: Path,
    ) -> None:
        dest = models_dir / model.name
        tmp = models_dir / f"{model.name}.tmp"

        # Skip if already downloaded
        if dest.is_file() and dest.stat().st_size > 0:
            logger.info("Model %s already exists, skipping", model.name)
            return

        logger.info("Starting download: %s from %s", model.name, model.url)
        try:
            await asyncio.to_thread(
                self._blocking_download,
                model.url,
                tmp,
            )
            # Atomic rename
            if dest.exists():
                dest.unlink()
            tmp.rename(dest)
            logger.info("Download complete: %s", model.name)
        except Exception:
            # Clean up partial file
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

    def _blocking_download(self, url: str, tmp_path: Path) -> None:
        """Synchronous download with progress tracking (runs in thread)."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AIHelpdeskAssistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            total = int(resp.headers.get("Content-Length", 0))
            self._state.bytes_total = total
            self._state.bytes_downloaded = 0

            with open(tmp_path, "wb") as f:
                while True:
                    if self._cancel_event.is_set():
                        msg = "Download cancelled by user"
                        raise RuntimeError(msg)
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    self._state.bytes_downloaded += len(chunk)

        if tmp_path.stat().st_size == 0:
            msg = f"Downloaded file is empty: {tmp_path.name}"
            raise RuntimeError(msg)
