"""Tests for health endpoints — public /health, token-gated /health/detail,
and localhost-only process-control endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Address

from app.main import create_app
from app.process_utils import find_pids_on_port, is_port_listening
from app.routers.health import _require_localhost
from tests.helpers import NETSTAT_SAMPLE_HEALTH, setup_app_state


def _make_client() -> AsyncClient:
    app = create_app()
    app.state.chroma_client = MagicMock()
    setup_app_state(app)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


# -- GET /health (public, minimal) ------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_returns_minimal_response(client: AsyncClient) -> None:
    """Public /health must NOT expose version or internal details."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"status"}
    assert "version" not in data
    assert "llm_reachable" not in data
    assert "chroma_ready" not in data


# -- GET /health/detail (token-gated) ---------------------------------------


@pytest.mark.asyncio
async def test_health_detail_unauthenticated_returns_200_when_no_token_configured(
    client: AsyncClient,
) -> None:
    """When api_token is empty (dev mode), /health/detail is accessible."""
    response = await client.get("/health/detail")
    assert response.status_code == 200
    data = response.json()
    required_keys = {"status", "llm_reachable", "embed_reachable", "chroma_ready", "chroma_doc_counts", "version"}
    assert required_keys.issubset(data.keys())


@pytest.mark.asyncio
async def test_health_detail_with_token_configured_requires_token(client: AsyncClient) -> None:
    """When api_token is set, /health/detail requires valid X-Extension-Token."""
    with patch("app.routers.health.settings") as mock_settings:
        mock_settings.api_token = "secret-token"
        mock_settings.llm_base_url = "http://localhost:11435"
        response = await client.get("/health/detail")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_detail_with_valid_token_returns_200(client: AsyncClient) -> None:
    with patch("app.routers.health.settings") as mock_settings:
        mock_settings.api_token = "secret-token"
        mock_settings.llm_base_url = "http://localhost:11435"
        mock_settings.version = "1.11.0"
        response = await client.get(
            "/health/detail",
            headers={"X-Extension-Token": "secret-token"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_degraded_when_llm_down(client: AsyncClient) -> None:
    response = await client.get("/health/detail")
    data = response.json()
    # In test environment LLM server is not running, so should be degraded
    assert data["status"] in ("ok", "degraded")
    assert isinstance(data["llm_reachable"], bool)


# -- _require_localhost helper -----------------------------------------------


def test_require_localhost_allows_127_0_0_1() -> None:
    request = MagicMock()
    request.client = Address("127.0.0.1", 12345)
    # Should not raise
    _require_localhost(request)


def test_require_localhost_allows_ipv6_loopback() -> None:
    request = MagicMock()
    request.client = Address("::1", 12345)
    # Should not raise
    _require_localhost(request)


def test_require_localhost_blocks_external_ip() -> None:
    request = MagicMock()
    request.client = Address("192.168.1.50", 12345)
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


def test_require_localhost_blocks_when_client_is_none() -> None:
    request = MagicMock()
    request.client = None
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


def test_require_localhost_blocks_remote_loopback_look_alike() -> None:
    request = MagicMock()
    request.client = Address("127.0.0.2", 12345)
    with pytest.raises(HTTPException) as exc_info:
        _require_localhost(request)
    assert exc_info.value.status_code == 403


# -- find_pids_on_port / is_port_listening -----------------------------------


def test_find_pids_on_port_finds_listening_pid() -> None:
    with patch("app.process_utils.subprocess.check_output", return_value=NETSTAT_SAMPLE_HEALTH):
        pids = find_pids_on_port(11435)
    assert pids == [5432]


def test_find_pids_on_port_no_match() -> None:
    with patch("app.process_utils.subprocess.check_output", return_value=NETSTAT_SAMPLE_HEALTH):
        pids = find_pids_on_port(9999)
    assert pids == []


def test_find_pids_on_port_subprocess_error() -> None:
    with patch("app.process_utils.subprocess.check_output", side_effect=OSError("fail")):
        pids = find_pids_on_port(11435)
    assert pids == []


def test_is_port_listening_true() -> None:
    with patch("app.process_utils.subprocess.check_output", return_value=NETSTAT_SAMPLE_HEALTH):
        assert is_port_listening(11435) is True


def test_is_port_listening_false() -> None:
    with patch("app.process_utils.subprocess.check_output", return_value=NETSTAT_SAMPLE_HEALTH):
        assert is_port_listening(9999) is False


# -- Process-control endpoints: smoke tests with mock localhost --------------


@pytest.mark.asyncio
async def test_shutdown_returns_200_from_localhost() -> None:
    """POST /shutdown is allowed from 127.0.0.1 (ASGITransport always uses loopback)."""
    async with _make_client() as ac:
        with patch("app.routers.health.asyncio.create_task"):
            response = await ac.post("/shutdown")
    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}


@pytest.mark.asyncio
async def test_llm_start_returns_already_running_when_both_up() -> None:
    """POST /llm/start returns already_running when both servers are up."""
    app = create_app()
    app.state.chroma_client = MagicMock()
    setup_app_state(app)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    app.state.llm_service._client.get = AsyncMock(return_value=mock_resp)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with patch("app.routers.health.is_port_listening", return_value=True):
            response = await ac.post("/llm/start")
    assert response.status_code == 200
    assert response.json()["status"] == "already_running"


@pytest.mark.asyncio
async def test_llm_start_starts_only_embed_when_llm_up() -> None:
    """POST /llm/start skips LLM start if healthy, starts embed if not listening."""
    app = create_app()
    app.state.chroma_client = MagicMock()
    setup_app_state(app)

    # LLM health check returns 200 (running)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    app.state.llm_service._client.get = AsyncMock(return_value=mock_resp)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with (
            patch("app.routers.health.is_port_listening", return_value=False),
            patch("app.routers.health._legacy_ollama_checked", True),
            patch("app.routers.health.subprocess.Popen") as mock_popen,
            patch("app.routers.health.resolve_llama_exe", return_value="llama-server"),
            patch("app.routers.health.detect_gpu_config", return_value=("-1", "8192")),
            patch("app.routers.health.MODELS_DIR") as mock_dir,
        ):
            mock_gguf = MagicMock()
            mock_dir.__truediv__ = MagicMock(return_value=mock_gguf)
            response = await ac.post("/llm/start")

    assert response.status_code == 200
    assert response.json()["status"] == "starting"
    # Only embed server Popen called (LLM was already running)
    assert mock_popen.call_count == 1
    call_args = mock_popen.call_args[0][0]
    assert "--embedding" in call_args


@pytest.mark.asyncio
async def test_llm_stop_returns_200() -> None:
    """POST /llm/stop uses port-targeted kill."""
    async with _make_client() as ac:
        with patch("app.routers.health.kill_pids_on_port", return_value=[]):
            response = await ac.post("/llm/stop")
    assert response.status_code == 200
    assert response.json() == {"status": "stopping"}


@pytest.mark.asyncio
async def test_llm_stop_kills_only_llm_port() -> None:
    """POST /llm/stop should call kill_pids_on_port with LLM port only."""
    async with _make_client() as ac:
        with patch(
            "app.routers.health.kill_pids_on_port",
            return_value=[1234],
        ) as mock_kill:
            response = await ac.post("/llm/stop")
    assert response.status_code == 200
    # Called with LLM port (11435), NOT embed port
    mock_kill.assert_called_once_with(11435)


# -- POST /llm/switch -------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_switch_valid_model() -> None:
    """POST /llm/switch with a valid model starts switching."""
    app = create_app()
    setup_app_state(app)
    app.state.current_llm_model = "qwen3.5:9b"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with (
            patch("app.routers.health.kill_pids_on_port", return_value=[]),
            patch("app.routers.health._probe_loaded_model", new_callable=AsyncMock, return_value=None),
            patch("app.routers.health.subprocess.Popen"),
            patch("app.routers.health.MODELS_DIR") as mock_dir,
            patch("app.routers.health.resolve_llama_exe", return_value="llama-server"),
            patch("app.routers.health.detect_gpu_config", return_value=("-1", "8192")),
            patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_gguf = MagicMock()
            mock_gguf.is_file.return_value = True
            mock_dir.__truediv__ = MagicMock(return_value=mock_gguf)
            response = await ac.post("/llm/switch", json={"model": "qwen3:14b"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "switching"
    assert data["model"] == "qwen3:14b"


@pytest.mark.asyncio
async def test_llm_switch_unknown_model_returns_404() -> None:
    """POST /llm/switch with an unknown model returns 404."""
    async with _make_client() as ac:
        with patch("app.routers.health._probe_loaded_model", new_callable=AsyncMock, return_value=None):
            response = await ac.post("/llm/switch", json={"model": "nonexistent:7b"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_llm_switch_already_loaded() -> None:
    """POST /llm/switch with the currently loaded model returns already_loaded."""
    app = create_app()
    setup_app_state(app)
    app.state.current_llm_model = "qwen3.5:9b"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with patch("app.routers.health._probe_loaded_model", new_callable=AsyncMock, return_value=None):
            response = await ac.post("/llm/switch", json={"model": "qwen3.5:9b"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already_loaded"
    assert data["model"] == "qwen3.5:9b"


@pytest.mark.asyncio
async def test_llm_switch_corrects_state_mismatch() -> None:
    """POST /llm/switch detects and corrects model state mismatch."""
    app = create_app()
    setup_app_state(app)
    # State says qwen3.5:9b but server actually has qwen3:14b
    app.state.current_llm_model = "qwen3.5:9b"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with patch(
            "app.routers.health._probe_loaded_model",
            new_callable=AsyncMock,
            return_value="qwen3:14b",
        ):
            # Request to switch to qwen3:14b — but server already has it
            response = await ac.post("/llm/switch", json={"model": "qwen3:14b"})

    assert response.status_code == 200
    data = response.json()
    # After correction, "qwen3:14b" == current, so already_loaded
    assert data["status"] == "already_loaded"
    assert data["model"] == "qwen3:14b"


@pytest.mark.asyncio
async def test_llm_switch_no_embed_restart() -> None:
    """POST /llm/switch should not kill or restart the embed server."""
    app = create_app()
    setup_app_state(app)
    app.state.current_llm_model = "qwen3.5:9b"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with (
            patch(
                "app.routers.health.kill_pids_on_port",
                return_value=[],
            ) as mock_kill,
            patch("app.routers.health._probe_loaded_model", new_callable=AsyncMock, return_value=None),
            patch("app.routers.health.subprocess.Popen") as mock_popen,
            patch("app.routers.health.MODELS_DIR") as mock_dir,
            patch("app.routers.health.resolve_llama_exe", return_value="llama-server"),
            patch("app.routers.health.detect_gpu_config", return_value=("-1", "8192")),
            patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_gguf = MagicMock()
            mock_gguf.is_file.return_value = True
            mock_dir.__truediv__ = MagicMock(return_value=mock_gguf)
            response = await ac.post("/llm/switch", json={"model": "qwen3:14b"})

    assert response.status_code == 200
    # kill_pids_on_port called only for LLM port
    mock_kill.assert_called_once_with(11435)
    # Only one Popen (LLM server), NOT two (no embed server restart)
    assert mock_popen.call_count == 1


# -- POST /llm/restart ------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_restart_returns_200() -> None:
    """POST /llm/restart kills LLM server and starts new one."""
    app = create_app()
    setup_app_state(app)
    app.state.current_llm_model = "qwen3.5:9b"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with (
            patch("app.routers.health.kill_pids_on_port", return_value=[1234]),
            patch("app.routers.health.is_port_listening", return_value=False),
            patch("app.routers.health.subprocess.Popen") as mock_popen,
            patch("app.routers.health.resolve_llama_exe", return_value="llama-server"),
            patch("app.routers.health.detect_gpu_config", return_value=("-1", "8192")),
            patch("app.routers.health.MODELS_DIR") as mock_dir,
        ):
            mock_gguf = MagicMock()
            mock_dir.__truediv__ = MagicMock(return_value=mock_gguf)
            response = await ac.post("/llm/restart")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "restarting"
    assert data["model"] == "qwen3.5:9b"
    assert mock_popen.call_count == 1


@pytest.mark.asyncio
async def test_llm_restart_waits_for_port_free() -> None:
    """POST /llm/restart polls until the port is free before starting."""
    app = create_app()
    setup_app_state(app)
    app.state.current_llm_model = "qwen3.5:9b"

    port_check_results = iter([True, True, False])

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        with (
            patch("app.routers.health.kill_pids_on_port", return_value=[1234]),
            patch("app.routers.health.is_port_listening", side_effect=port_check_results),
            patch("app.routers.health.subprocess.Popen"),
            patch("app.routers.health.resolve_llama_exe", return_value="llama-server"),
            patch("app.routers.health.detect_gpu_config", return_value=("-1", "8192")),
            patch("app.routers.health.MODELS_DIR") as mock_dir,
            patch("app.routers.health.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_gguf = MagicMock()
            mock_dir.__truediv__ = MagicMock(return_value=mock_gguf)
            response = await ac.post("/llm/restart")

    assert response.status_code == 200
    # Slept twice waiting for port to free (True, True, then False)
    assert mock_sleep.call_count == 2
