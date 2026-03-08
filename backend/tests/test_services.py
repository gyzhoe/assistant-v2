"""Unit tests for LLMService and EmbedService.

LLMService tests target the async ``_generate_async`` method via
``generate()`` (the public entry-point), using a mock ``httpx.AsyncClient``.

EmbedService tests exercise both the async ``_embed_async`` path (via a mock
``httpx.AsyncClient``) and the sync ``_embed_sync`` path (via a mock
``httpx.Client``) since the service supports both client types.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.constants import LLMModelError
from app.services.embed_service import EmbedService
from app.services.llm_service import LLMService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    status_code: int = 200,
    body: str | None = None,
    json_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock httpx.Response with controllable json() / text behaviour."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()

    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    elif body is not None:
        resp.json = MagicMock(side_effect=json.JSONDecodeError("bad json", body, 0))
    else:
        resp.json = MagicMock(return_value={})

    return resp


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a minimal HTTPStatusError for the given status code."""
    request = httpx.Request("POST", "http://localhost:11435/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Server error {status_code}",
        request=request,
        response=response,
    )


def _mock_async_client() -> MagicMock:
    """Create a mock httpx.AsyncClient."""
    mock = MagicMock(spec=httpx.AsyncClient)
    mock.post = AsyncMock()
    mock.get = AsyncMock()
    mock.base_url = httpx.URL("http://localhost:11435")
    return mock


def _mock_sync_client() -> MagicMock:
    """Create a mock httpx.Client."""
    return MagicMock(spec=httpx.Client)


# ---------------------------------------------------------------------------
# LLMService tests
# ---------------------------------------------------------------------------


class TestLLMServiceGenerateAsync:
    """Unit tests for LLMService._generate_async (via generate())."""

    def _svc(self) -> tuple[LLMService, MagicMock]:
        mock_client = _mock_async_client()
        svc = LLMService(client=mock_client)
        return svc, mock_client

    # --- happy path ---

    @pytest.mark.asyncio
    async def test_successful_generation_returns_text(self) -> None:
        """A well-formed response returns the generated text."""
        svc, mock_client = self._svc()
        mock_resp = _make_response(json_data={
            "choices": [{"message": {"content": "Here is the fix."}}],
        })
        mock_client.post.return_value = mock_resp

        result = await svc.generate("Describe the issue.", "llama3.2:3b")

        assert result == "Here is the fix."

    @pytest.mark.asyncio
    async def test_successful_generation_posts_correct_payload(self) -> None:
        """generate sends the right JSON body to the LLM server."""
        svc, mock_client = self._svc()
        mock_resp = _make_response(json_data={
            "choices": [{"message": {"content": "ok"}}],
        })
        mock_client.post.return_value = mock_resp

        await svc.generate("my prompt", "qwen2.5:14b")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert sent_json["model"] == "qwen2.5:14b"
        assert sent_json["messages"] == [{"role": "user", "content": "my prompt"}]
        assert sent_json["stream"] is False

        # Verify sampling options are included at top level
        assert "temperature" in sent_json
        assert "top_p" in sent_json
        assert "top_k" in sent_json
        assert "repeat_penalty" in sent_json
        assert "max_tokens" in sent_json

    # --- connection errors ---

    @pytest.mark.asyncio
    async def test_connect_error_raises_connection_error(self) -> None:
        """httpx.ConnectError is converted to ConnectionError."""
        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ConnectionError, match="LLM server unreachable"):
            await svc.generate("prompt", "llama3.2:3b")

    @pytest.mark.asyncio
    async def test_connect_error_message_contains_base_url(self) -> None:
        """ConnectionError message references the configured base URL."""
        from app.config import settings

        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ConnectionError) as exc_info:
            await svc.generate("prompt", "llama3.2:3b")

        assert settings.llm_base_url in str(exc_info.value)

    # --- timeout ---

    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self) -> None:
        """httpx.ReadTimeout is converted to ConnectionError."""
        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ReadTimeout("timed out")

        with pytest.raises(ConnectionError, match="timed out"):
            await svc.generate("prompt", "llama3.2:3b")

    @pytest.mark.asyncio
    async def test_connect_timeout_raises_connection_error(self) -> None:
        """httpx.ConnectTimeout (a TimeoutException subclass) is also caught."""
        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ConnectTimeout("connect timed out")

        with pytest.raises(ConnectionError):
            await svc.generate("prompt", "llama3.2:3b")

    # --- HTTP error status ---

    @pytest.mark.asyncio
    async def test_http_status_error_raises_llm_model_error(self) -> None:
        """An HTTP 500 from the LLM server is converted to LLMModelError."""
        svc, mock_client = self._svc()
        http_err = _make_http_status_error(500)
        mock_resp = _make_response(status_code=500)
        mock_resp.raise_for_status.side_effect = http_err
        mock_client.post.return_value = mock_resp

        with pytest.raises(LLMModelError, match="500"):
            await svc.generate("prompt", "llama3.2:3b")

    @pytest.mark.asyncio
    async def test_http_status_error_contains_model_name(self) -> None:
        """LLMModelError message includes the model name for debugging."""
        svc, mock_client = self._svc()
        http_err = _make_http_status_error(404)
        mock_resp = _make_response(status_code=404)
        mock_resp.raise_for_status.side_effect = http_err
        mock_client.post.return_value = mock_resp

        with pytest.raises(LLMModelError) as exc_info:
            await svc.generate("prompt", "nonexistent-model:7b")

        assert "nonexistent-model:7b" in str(exc_info.value)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_http_status_error_not_retried(self) -> None:
        """LLMModelError should not trigger retries (model errors aren't transient)."""
        svc, mock_client = self._svc()
        http_err = _make_http_status_error(404)
        mock_resp = _make_response(status_code=404)
        mock_resp.raise_for_status.side_effect = http_err
        mock_client.post.return_value = mock_resp

        with pytest.raises(LLMModelError):
            await svc.generate("prompt", "llama3.2:3b")

        # Should only be called once — no retries for model errors
        assert mock_client.post.call_count == 1

    # --- JSON parse errors ---

    @pytest.mark.asyncio
    async def test_invalid_json_response_raises_connection_error(self) -> None:
        """A non-JSON body causes ConnectionError (json.JSONDecodeError caught)."""
        svc, mock_client = self._svc()
        mock_resp = _make_response(body="not-json")
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError, match="invalid or missing"):
            await svc.generate("prompt", "llama3.2:3b")

    # --- missing key ---

    @pytest.mark.asyncio
    async def test_missing_response_key_raises_connection_error(self) -> None:
        """Valid JSON without 'choices' key raises ConnectionError (KeyError caught)."""
        svc, mock_client = self._svc()
        mock_resp = _make_response(json_data={"model": "llama3.2:3b", "done": True})
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError, match="invalid or missing"):
            await svc.generate("prompt", "llama3.2:3b")


# ---------------------------------------------------------------------------
# EmbedService tests — sync path (httpx.Client)
# ---------------------------------------------------------------------------


class TestEmbedServiceEmbedSync:
    """Unit tests for EmbedService._embed_sync (sync httpx.Client path)."""

    def _svc(self, model: str = "nomic-embed-text") -> EmbedService:
        svc = EmbedService(client=_mock_sync_client(), model=model)
        return svc

    # --- happy path ---

    def test_successful_embedding_returns_float_list(self) -> None:
        """A well-formed response returns the embedding as list[float]."""
        svc = self._svc()
        embedding = [0.1, 0.2, 0.3, 0.4]
        mock_resp = _make_response(json_data={
            "data": [{"embedding": embedding}],
        })
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        result = svc._embed_sync("some text")

        assert result == embedding
        assert all(isinstance(v, float) for v in result)

    def test_successful_embedding_posts_correct_payload(self) -> None:
        """_embed_sync sends model and input fields to the embed server."""
        svc = self._svc(model="nomic-embed-text")
        mock_resp = _make_response(json_data={
            "data": [{"embedding": [0.5]}],
        })
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        svc._embed_sync("hello world")

        call_kwargs = svc._client.post.call_args
        assert call_kwargs is not None
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert sent_json["model"] == "nomic-embed-text"
        assert sent_json["input"] == "search_document: hello world"

    # --- connection errors ---

    def test_connect_error_raises_connection_error(self) -> None:
        """httpx.ConnectError is converted to ConnectionError."""
        svc = self._svc()
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ConnectionError, match="unreachable"):
            svc._embed_sync("text")

    def test_connect_error_message_contains_base_url(self) -> None:
        """ConnectionError message references the configured base URL."""
        from app.config import settings

        svc = self._svc()
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ConnectionError) as exc_info:
            svc._embed_sync("text")

        assert settings.embed_base_url in str(exc_info.value)

    # --- timeout ---

    def test_timeout_raises_connection_error(self) -> None:
        """httpx.ReadTimeout is converted to ConnectionError."""
        svc = self._svc()
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.side_effect = httpx.ReadTimeout("timed out")

        with pytest.raises(ConnectionError, match="timed out"):
            svc._embed_sync("text")

    # --- HTTP error status ---

    def test_http_status_error_raises_llm_model_error(self) -> None:
        """An HTTP 404 from the embed server is converted to LLMModelError."""
        svc = self._svc()
        http_err = _make_http_status_error(404)
        mock_resp = _make_response(status_code=404)
        mock_resp.raise_for_status.side_effect = http_err
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        with pytest.raises(LLMModelError, match="404"):
            svc._embed_sync("text")

    def test_http_status_error_contains_model_name(self) -> None:
        """LLMModelError message includes the model name."""
        svc = self._svc(model="nomic-embed-text")
        http_err = _make_http_status_error(404)
        mock_resp = _make_response(status_code=404)
        mock_resp.raise_for_status.side_effect = http_err
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        with pytest.raises(LLMModelError) as exc_info:
            svc._embed_sync("text")

        assert "nomic-embed-text" in str(exc_info.value)
        assert exc_info.value.status_code == 404

    # --- JSON parse errors ---

    def test_invalid_json_response_raises_connection_error(self) -> None:
        """A non-JSON body causes ConnectionError (json.JSONDecodeError caught)."""
        svc = self._svc()
        mock_resp = _make_response(body="not-json")
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        with pytest.raises(ConnectionError, match="invalid or missing"):
            svc._embed_sync("text")

    # --- missing embedding key ---

    def test_missing_embedding_key_raises_connection_error(self) -> None:
        """Valid JSON without expected nested key raises ConnectionError."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"model": "nomic-embed-text"})
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        with pytest.raises(ConnectionError, match="missing expected key"):
            svc._embed_sync("text")

    def test_missing_embedding_key_error_lists_present_keys(self) -> None:
        """The ConnectionError message lists the actual keys returned."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"status": "error", "message": "model not found"})
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        with pytest.raises(ConnectionError) as exc_info:
            svc._embed_sync("text")

        # The service includes list(data.keys()) in the message
        error_msg = str(exc_info.value)
        assert "status" in error_msg or "message" in error_msg

    # --- empty embedding ---

    def test_empty_embedding_list_is_returned_as_is(self) -> None:
        """An empty embedding vector is returned without error."""
        svc = self._svc()
        mock_resp = _make_response(json_data={
            "data": [{"embedding": []}],
        })
        assert isinstance(svc._client, httpx.Client)
        svc._client.post.return_value = mock_resp

        result = svc._embed_sync("text")

        assert result == []


# ---------------------------------------------------------------------------
# EmbedService tests — async path (httpx.AsyncClient)
# ---------------------------------------------------------------------------


class TestEmbedServiceEmbedAsync:
    """Unit tests for EmbedService._embed_async (async httpx.AsyncClient path)."""

    def _svc(self, model: str = "nomic-embed-text") -> tuple[EmbedService, MagicMock]:
        mock_client = _mock_async_client()
        svc = EmbedService(client=mock_client, model=model)
        return svc, mock_client

    @pytest.mark.asyncio
    async def test_successful_embedding_returns_float_list(self) -> None:
        svc, mock_client = self._svc()
        embedding = [0.1, 0.2, 0.3, 0.4]
        mock_resp = _make_response(json_data={
            "data": [{"embedding": embedding}],
        })
        mock_client.post.return_value = mock_resp

        result = await svc.embed("some text")
        assert result == embedding

    @pytest.mark.asyncio
    async def test_connect_error_raises_connection_error(self) -> None:
        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ConnectionError, match="unreachable"):
            await svc.embed("text")

    @pytest.mark.asyncio
    async def test_timeout_raises_connection_error(self) -> None:
        svc, mock_client = self._svc()
        mock_client.post.side_effect = httpx.ReadTimeout("timed out")

        with pytest.raises(ConnectionError, match="timed out"):
            await svc.embed("text")

    @pytest.mark.asyncio
    async def test_missing_embedding_key_raises_connection_error(self) -> None:
        svc, mock_client = self._svc()
        mock_resp = _make_response(json_data={"model": "nomic-embed-text"})
        mock_client.post.return_value = mock_resp

        with pytest.raises(ConnectionError, match="missing expected key"):
            await svc.embed("text")

    def test_embed_fn_raises_on_async_client(self) -> None:
        """embed_fn (sync) should raise TypeError when client is async."""
        svc, _ = self._svc()
        with pytest.raises(TypeError, match="embed_fn.*not available"):
            _ = svc.embed_fn


# ---------------------------------------------------------------------------
# LLMService._prepare_prompt tests
# ---------------------------------------------------------------------------


class TestPreparePrompt:
    """Tests for conditional /no_think suffix on Qwen3 models."""

    def test_qwen3_gets_no_think_suffix(self) -> None:
        """Qwen3 models (thinking=1 by default) get /no_think appended."""
        result = LLMService._prepare_prompt("Hello", "qwen3:14b")
        assert result == "Hello /no_think"

    def test_qwen3_case_insensitive(self) -> None:
        """Model name matching is case-insensitive."""
        result = LLMService._prepare_prompt("Hello", "Qwen3:14b")
        assert result == "Hello /no_think"

    def test_qwen35_no_suffix(self) -> None:
        """Qwen3.5 models (thinking=0 by default) do NOT get the suffix."""
        result = LLMService._prepare_prompt("Hello", "qwen3.5:9b")
        assert result == "Hello"

    def test_qwen35_uppercase_no_suffix(self) -> None:
        """Qwen3.5 case-insensitive — still no suffix."""
        result = LLMService._prepare_prompt("Hello", "Qwen3.5:9b")
        assert result == "Hello"

    def test_other_model_no_suffix(self) -> None:
        """Non-Qwen models get no suffix."""
        result = LLMService._prepare_prompt("Hello", "llama3.2:3b")
        assert result == "Hello"

    def test_empty_model_no_suffix(self) -> None:
        """Empty model name does not crash."""
        result = LLMService._prepare_prompt("Hello", "")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_generate_sends_prepared_prompt_for_qwen3(self) -> None:
        """generate() applies _prepare_prompt before sending to server."""
        mock_client = _mock_async_client()
        svc = LLMService(client=mock_client)
        mock_resp = _make_response(json_data={
            "choices": [{"message": {"content": "ok"}}],
        })
        mock_client.post.return_value = mock_resp

        await svc.generate("Describe the issue.", "qwen3:14b")

        call_kwargs = mock_client.post.call_args
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        content = sent_json["messages"][0]["content"]
        assert content.endswith(" /no_think")

    @pytest.mark.asyncio
    async def test_generate_no_suffix_for_qwen35(self) -> None:
        """generate() does NOT append /no_think for qwen3.5 models."""
        mock_client = _mock_async_client()
        svc = LLMService(client=mock_client)
        mock_resp = _make_response(json_data={
            "choices": [{"message": {"content": "ok"}}],
        })
        mock_client.post.return_value = mock_resp

        await svc.generate("Describe the issue.", "qwen3.5:9b")

        call_kwargs = mock_client.post.call_args
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        content = sent_json["messages"][0]["content"]
        assert not content.endswith(" /no_think")
        assert content == "Describe the issue."
