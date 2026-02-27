"""Unit tests for LLMService and EmbedService.

Tests target the synchronous _generate_sync / _embed_sync methods directly,
avoiding asyncio.to_thread so we can exercise error handling without a running
event loop.  httpx.Client is patched at the class level so no real network
calls are made.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

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
    request = httpx.Request("POST", "http://localhost:11434/api/generate")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Server error {status_code}",
        request=request,
        response=response,
    )


# ---------------------------------------------------------------------------
# LLMService tests
# ---------------------------------------------------------------------------


class TestLLMServiceGenerateSync:
    """Unit tests for LLMService._generate_sync."""

    def _svc(self) -> LLMService:
        return LLMService()

    # --- happy path ---

    def test_successful_generation_returns_text(self) -> None:
        """A well-formed Ollama response returns the 'response' field as a string."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"response": "Here is the fix."})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = svc._generate_sync("Describe the issue.", "llama3.2:3b")

        assert result == "Here is the fix."

    def test_successful_generation_posts_correct_payload(self) -> None:
        """_generate_sync sends the right JSON body to Ollama including options."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"response": "ok"})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            svc._generate_sync("my prompt", "qwen2.5:14b")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert sent_json["model"] == "qwen2.5:14b"
        assert sent_json["prompt"] == "my prompt"
        assert sent_json["stream"] is False

        # Verify sampling options are included
        options = sent_json["options"]
        assert "temperature" in options
        assert "top_p" in options
        assert "top_k" in options
        assert "repeat_penalty" in options
        assert "num_predict" in options

    # --- connection errors ---

    def test_connect_error_raises_connection_error(self) -> None:
        """httpx.ConnectError is converted to ConnectionError."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="Ollama service unreachable"):
                svc._generate_sync("prompt", "llama3.2:3b")

    def test_connect_error_message_contains_base_url(self) -> None:
        """ConnectionError message references the configured base URL."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError) as exc_info:
                svc._generate_sync("prompt", "llama3.2:3b")

        assert svc.base_url in str(exc_info.value)

    # --- timeout ---

    def test_timeout_raises_connection_error(self) -> None:
        """httpx.ReadTimeout is converted to ConnectionError."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ReadTimeout("timed out")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="timed out"):
                svc._generate_sync("prompt", "llama3.2:3b")

    def test_connect_timeout_raises_connection_error(self) -> None:
        """httpx.ConnectTimeout (a TimeoutException subclass) is also caught."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectTimeout("connect timed out")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError):
                svc._generate_sync("prompt", "llama3.2:3b")

    # --- HTTP error status ---

    def test_http_status_error_raises_connection_error(self) -> None:
        """An HTTP 500 from Ollama is converted to ConnectionError."""
        svc = self._svc()
        http_err = _make_http_status_error(500)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_resp = _make_response(status_code=500)
            mock_resp.raise_for_status.side_effect = http_err
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="500"):
                svc._generate_sync("prompt", "llama3.2:3b")

    # --- JSON parse errors ---

    def test_invalid_json_response_raises_connection_error(self) -> None:
        """A non-JSON body causes ConnectionError (json.JSONDecodeError caught)."""
        svc = self._svc()
        mock_resp = _make_response(body="not-json")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="invalid or missing"):
                svc._generate_sync("prompt", "llama3.2:3b")

    # --- missing key ---

    def test_missing_response_key_raises_connection_error(self) -> None:
        """Valid JSON without 'response' key raises ConnectionError (KeyError caught)."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"model": "llama3.2:3b", "done": True})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="invalid or missing"):
                svc._generate_sync("prompt", "llama3.2:3b")


# ---------------------------------------------------------------------------
# EmbedService tests
# ---------------------------------------------------------------------------


class TestEmbedServiceEmbedSync:
    """Unit tests for EmbedService._embed_sync."""

    def _svc(self, model: str = "nomic-embed-text") -> EmbedService:
        return EmbedService(model=model)

    # --- happy path ---

    def test_successful_embedding_returns_float_list(self) -> None:
        """A well-formed Ollama response returns the embedding as list[float]."""
        svc = self._svc()
        embedding = [0.1, 0.2, 0.3, 0.4]
        mock_resp = _make_response(json_data={"embedding": embedding})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = svc._embed_sync("some text")

        assert result == embedding
        assert all(isinstance(v, float) for v in result)

    def test_successful_embedding_posts_correct_payload(self) -> None:
        """_embed_sync sends model and prompt fields to Ollama."""
        svc = self._svc(model="nomic-embed-text")
        mock_resp = _make_response(json_data={"embedding": [0.5]})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            svc._embed_sync("hello world")

        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        sent_json: dict[str, Any] = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert sent_json["model"] == "nomic-embed-text"
        assert sent_json["prompt"] == "hello world"

    # --- connection errors ---

    def test_connect_error_raises_connection_error(self) -> None:
        """httpx.ConnectError is converted to ConnectionError."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="unreachable"):
                svc._embed_sync("text")

    def test_connect_error_message_contains_base_url(self) -> None:
        """ConnectionError message references the configured base URL."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError) as exc_info:
                svc._embed_sync("text")

        assert svc.base_url in str(exc_info.value)

    # --- timeout ---

    def test_timeout_raises_connection_error(self) -> None:
        """httpx.ReadTimeout is converted to ConnectionError."""
        svc = self._svc()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ReadTimeout("timed out")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="timed out"):
                svc._embed_sync("text")

    # --- HTTP error status ---

    def test_http_status_error_raises_connection_error(self) -> None:
        """An HTTP 404 from Ollama is converted to ConnectionError."""
        svc = self._svc()
        http_err = _make_http_status_error(404)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_resp = _make_response(status_code=404)
            mock_resp.raise_for_status.side_effect = http_err
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="404"):
                svc._embed_sync("text")

    # --- JSON parse errors ---

    def test_invalid_json_response_raises_connection_error(self) -> None:
        """A non-JSON body causes ConnectionError (json.JSONDecodeError caught)."""
        svc = self._svc()
        mock_resp = _make_response(body="not-json")

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="invalid or missing"):
                svc._embed_sync("text")

    # --- missing embedding key ---

    def test_missing_embedding_key_raises_connection_error(self) -> None:
        """Valid JSON without 'embedding' key raises ConnectionError."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"model": "nomic-embed-text"})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError, match="missing 'embedding' key"):
                svc._embed_sync("text")

    def test_missing_embedding_key_error_lists_present_keys(self) -> None:
        """The ConnectionError message lists the actual keys returned by Ollama."""
        svc = self._svc()
        mock_resp = _make_response(json_data={"status": "error", "message": "model not found"})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ConnectionError) as exc_info:
                svc._embed_sync("text")

        # The service includes list(data.keys()) in the message
        error_msg = str(exc_info.value)
        assert "status" in error_msg or "message" in error_msg

    # --- empty embedding ---

    def test_empty_embedding_list_is_returned_as_is(self) -> None:
        """An empty embedding vector from Ollama is returned without error.

        The service does not validate embedding dimensionality; callers that
        depend on a minimum length should validate at the call site (e.g.
        RAGService).  This test documents the current contract.
        """
        svc = self._svc()
        mock_resp = _make_response(json_data={"embedding": []})

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = svc._embed_sync("text")

        assert result == []
