"""Tests for app.services.process_control — subprocess launcher, legacy
Ollama check, and model probing logic extracted from health.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.process_control import (
    check_legacy_ollama,
    is_legacy_ollama_checked,
    launch_llama_server,
    probe_loaded_model,
)

# -- launch_llama_server -----------------------------------------------------


def test_launch_llama_server_basic_llm() -> None:
    """launch_llama_server builds correct command for LLM server."""
    with patch(
        "app.services.process_control.subprocess.Popen",
    ) as mock_popen:
        launch_llama_server(
            exe="llama-server",
            model_path="/models/model.gguf",
            port=11435,
            n_gpu_layers="-1",
            ctx_size="8192",
        )

    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert cmd[0] == "llama-server"
    assert "-m" in cmd
    assert "/models/model.gguf" in cmd
    assert "--port" in cmd
    assert "11435" in cmd
    assert "--n-gpu-layers" in cmd
    assert "-1" in cmd
    assert "--ctx-size" in cmd
    assert "8192" in cmd
    assert "--embedding" not in cmd


def test_launch_llama_server_embedding_mode() -> None:
    """launch_llama_server adds --embedding flag when embedding=True."""
    with patch(
        "app.services.process_control.subprocess.Popen",
    ) as mock_popen:
        launch_llama_server(
            exe="llama-server",
            model_path="/models/embed.gguf",
            port=11436,
            n_gpu_layers="-1",
            embedding=True,
        )

    cmd = mock_popen.call_args[0][0]
    assert "--embedding" in cmd
    assert "--ctx-size" not in cmd  # ctx_size is None by default


def test_launch_llama_server_no_ctx_size() -> None:
    """launch_llama_server omits --ctx-size when ctx_size is None."""
    with patch(
        "app.services.process_control.subprocess.Popen",
    ) as mock_popen:
        launch_llama_server(
            exe="llama-server",
            model_path="/models/model.gguf",
            port=11435,
            n_gpu_layers="0",
            ctx_size=None,
        )

    cmd = mock_popen.call_args[0][0]
    assert "--ctx-size" not in cmd


# -- check_legacy_ollama / is_legacy_ollama_checked --------------------------


@pytest.mark.asyncio
async def test_check_legacy_ollama_sets_flag() -> None:
    """check_legacy_ollama calls kill_legacy_ollama and sets the flag."""
    with patch(
        "app.services.process_control.kill_legacy_ollama",
    ) as mock_kill:
        # Reset module-level flag for test isolation
        import app.services.process_control as pc
        pc._legacy_ollama_checked = False
        try:
            assert is_legacy_ollama_checked() is False
            await check_legacy_ollama()
            assert is_legacy_ollama_checked() is True
            mock_kill.assert_called_once()
        finally:
            pc._legacy_ollama_checked = False


# -- probe_loaded_model ------------------------------------------------------


@pytest.mark.asyncio
async def test_probe_loaded_model_returns_display_name() -> None:
    """probe_loaded_model maps GGUF filename to display name."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "Qwen3.5-9B-Q4_K_M.gguf"}],
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await probe_loaded_model(mock_client)
    assert result == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_probe_loaded_model_returns_none_on_error() -> None:
    """probe_loaded_model returns None when the server is unreachable."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    result = await probe_loaded_model(mock_client)
    assert result is None


@pytest.mark.asyncio
async def test_probe_loaded_model_returns_none_on_empty_models() -> None:
    """probe_loaded_model returns None when no models are loaded."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": []}
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await probe_loaded_model(mock_client)
    assert result is None


@pytest.mark.asyncio
async def test_probe_loaded_model_resolves_basename() -> None:
    """probe_loaded_model resolves full-path model IDs by basename."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "/some/path/Qwen3.5-9B-Q4_K_M.gguf"}],
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await probe_loaded_model(mock_client)
    assert result == "qwen3.5:9b"
