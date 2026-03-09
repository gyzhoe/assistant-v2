import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.models.request_models import GenerateRequest, NoteItem
from app.routers.generate import _build_prompt, _format_notes_section, _relevance_label
from app.services.microsoft_docs import WebContextDoc
from tests.helpers import apply_services, create_mock_services, mock_ms_docs


@pytest.mark.asyncio
async def test_generate_without_subject_returns_200(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="VPN fix applied.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_description": "Cannot login to VPN",
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "VPN fix applied."


@pytest.mark.asyncio
async def test_generate_without_description_returns_200(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="VPN issue resolved.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "VPN Issue",
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "VPN issue resolved."


@pytest.mark.asyncio
async def test_generate_returns_reply(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Hi Alex, here is the fix...")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "Cannot access network drive",
        "ticket_description": "Network drive not accessible after password reset",
        "requester_name": "Alex Johnson",
        "category": "Network",
        "status": "Open",
    })
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["reply"] == "Hi Alex, here is the fix..."
    assert "model_used" in data
    assert "context_docs" in data
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_generate_llm_down_returns_503(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(
        side_effect=ConnectionError("LLM server unreachable at http://localhost:11435")
    )
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "ticket_description": "Test description",
    })
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_generate_with_web_context(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """MS Learn docs should appear in the prompt sent to the LLM."""
    web_docs = [
        WebContextDoc(title="802.1X Setup Guide", url="https://learn.microsoft.com/802x", content="Enable 802.1X via Group Policy."),
    ]
    mock_rag, mock_llm, _ = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Here is the fix.")
    mock_ms = mock_ms_docs(return_value=web_docs)
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "802.1X not working",
        "category": "NETWORK CONNECTION",
        "include_web_context": True,
    })
    assert response.status_code == 200

    # Verify the web context was included in the prompt
    prompt_arg = mock_llm.generate.call_args.kwargs["prompt"]
    assert "[WEB | Microsoft Learn]" in prompt_arg
    assert "802.1X Setup Guide" in prompt_arg
    assert "Enable 802.1X via Group Policy." in prompt_arg


@pytest.mark.asyncio
async def test_generate_web_context_disabled(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """When include_web_context is false, MicrosoftDocsService.search should not be called."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Reply without web context.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "ticket_description": "Test",
        "include_web_context": False,
    })
    assert response.status_code == 200
    mock_ms.search.assert_not_called()


@pytest.mark.asyncio
async def test_generate_web_context_failure_still_generates(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """If MS Learn search returns empty (graceful degradation), reply should still be generated."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Reply without web context.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "VPN issue",
        "category": "Network",
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "Reply without web context."


@pytest.mark.asyncio
async def test_generate_ms_docs_config_disabled(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """When settings.microsoft_docs_enabled is False, search should not be called."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Reply with config disabled.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    with patch("app.routers.generate.settings") as mock_settings:
        mock_settings.microsoft_docs_enabled = False

        response = await client.post("/generate", json={
            "ticket_subject": "Test",
            "include_web_context": True,
        })
        assert response.status_code == 200
        mock_ms.search.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests for _build_prompt and _relevance_label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_does_not_log_ticket_subject(
    test_app: FastAPI, client: AsyncClient, caplog: pytest.LogCaptureFixture,
) -> None:
    """The generate endpoint should NOT log raw ticket subjects (PII)."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    subject = "John Doe cannot access VPN"
    with caplog.at_level(logging.INFO, logger="app.routers.generate"):
        await client.post("/generate", json={
            "ticket_subject": subject,
            "ticket_description": "Details here",
        })

    # The raw subject should NOT appear in logs
    for record in caplog.records:
        assert subject not in record.getMessage()
    # But subject_len should appear
    log_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "subject_len=" in log_messages


class TestRelevanceLabel:
    """Tests for _relevance_label() helper."""

    def test_high_relevance(self) -> None:
        assert _relevance_label(0.75) == "HIGH relevance"
        assert _relevance_label(0.90) == "HIGH relevance"
        assert _relevance_label(1.0) == "HIGH relevance"

    def test_moderate_relevance(self) -> None:
        assert _relevance_label(0.50) == "MODERATE relevance"
        assert _relevance_label(0.60) == "MODERATE relevance"
        assert _relevance_label(0.74) == "MODERATE relevance"

    def test_low_relevance(self) -> None:
        assert _relevance_label(0.49) == "LOW relevance"
        assert _relevance_label(0.35) == "LOW relevance"
        assert _relevance_label(0.0) == "LOW relevance"


class TestBuildPrompt:
    """Tests for _build_prompt() prompt structure."""

    def _request(self, **kwargs: str) -> GenerateRequest:
        defaults = {
            "ticket_subject": "VPN Issue",
            "ticket_description": "Cannot connect to VPN",
            "requester_name": "Jane",
            "category": "Network",
            "status": "Open",
        }
        defaults.update(kwargs)
        return GenerateRequest(**defaults)

    def test_contains_grounding_rules(self) -> None:
        prompt = _build_prompt(self._request(), "some KB context")
        assert "GROUNDING RULES" in prompt
        assert "NEVER invent" in prompt
        assert "ONLY use information" in prompt
        assert "untrusted user input" in prompt

    def test_contains_format_rules(self) -> None:
        prompt = _build_prompt(self._request(), "some KB context")
        assert "FORMAT RULES" in prompt
        assert "60-120 words" in prompt

    def test_contains_examples(self) -> None:
        prompt = _build_prompt(self._request(), "some KB context")
        assert "EXAMPLES" in prompt
        assert "Example 1" in prompt
        assert "Example 2" in prompt

    def test_no_context_fallback(self) -> None:
        prompt = _build_prompt(self._request(), "")
        assert "(no matching articles found)" in prompt

    def test_context_included_when_provided(self) -> None:
        prompt = _build_prompt(self._request(), "[KB | HIGH relevance | score: 0.85]\nReset VPN")
        assert "HIGH relevance" in prompt
        assert "Reset VPN" in prompt

    def test_xml_delimiters_wrap_user_content(self) -> None:
        """Prompt injection defense: user content should be wrapped in XML tags."""
        req = self._request(
            ticket_subject="My VPN is broken",
            ticket_description="Cannot connect since Tuesday",
        )
        prompt = _build_prompt(req, "some context")
        assert "<user_ticket_subject>My VPN is broken</user_ticket_subject>" in prompt
        assert "<user_ticket_description>Cannot connect since Tuesday</user_ticket_description>" in prompt
        assert "<user_custom_fields>" in prompt
        assert "</user_custom_fields>" in prompt

    def test_prompt_suffix_wrapped_in_xml_tags(self) -> None:
        """prompt_suffix user input should be delimited."""
        req = self._request()
        req.prompt_suffix = "Be more concise"
        prompt = _build_prompt(req, "context")
        # The prompt_suffix is wrapped by the caller, not _build_prompt.
        # Verify the main prompt has the XML structure.
        assert "<user_ticket_subject>" in prompt


# ---------------------------------------------------------------------------
# RI2: custom_fields validation
# ---------------------------------------------------------------------------


class TestCustomFieldsValidation:
    """Tests for custom_fields length/count limits on GenerateRequest."""

    def test_valid_custom_fields(self) -> None:
        req = GenerateRequest(custom_fields={"Building": "A1", "Room": "101"})
        assert req.custom_fields == {"Building": "A1", "Room": "101"}

    def test_too_many_keys(self) -> None:
        fields = {f"key_{i}": "val" for i in range(11)}
        with pytest.raises(ValueError, match="maximum 10 keys"):
            GenerateRequest(custom_fields=fields)

    def test_key_too_long(self) -> None:
        with pytest.raises(ValueError, match="key too long"):
            GenerateRequest(custom_fields={"x" * 101: "val"})

    def test_value_too_long(self) -> None:
        with pytest.raises(ValueError, match="value too long"):
            GenerateRequest(custom_fields={"key": "x" * 501})

    def test_control_chars_stripped(self) -> None:
        req = GenerateRequest(
            custom_fields={"key\x00": "val\x01ue"},
        )
        assert req.custom_fields == {"key": "value"}

    def test_newline_tab_preserved(self) -> None:
        req = GenerateRequest(
            custom_fields={"key": "line1\nline2\ttab"},
        )
        assert req.custom_fields["key"] == "line1\nline2\ttab"


# ---------------------------------------------------------------------------
# Notes feature tests
# ---------------------------------------------------------------------------

_SAMPLE_NOTES = [
    {"author": "Jane Doe", "text": "VPN keeps dropping", "type": "client", "date": "2026-03-01"},
    {"author": "Tech A", "text": "Checked VPN config", "type": "tech_visible", "date": "2026-03-02"},
]


@pytest.mark.asyncio
async def test_generate_with_notes(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """POST /generate with valid notes returns 200."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    mock_llm.generate = AsyncMock(return_value="Fix applied.")
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "VPN Issue",
        "ticket_description": "VPN dropping",
        "notes": _SAMPLE_NOTES,
    })
    assert response.status_code == 200
    assert response.json()["reply"] == "Fix applied."


@pytest.mark.asyncio
async def test_generate_notes_in_prompt(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """Note text should appear in the prompt sent to the LLM."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "VPN Issue",
        "ticket_description": "VPN dropping",
        "notes": _SAMPLE_NOTES,
    })
    assert response.status_code == 200

    prompt_arg = mock_llm.generate.call_args.kwargs["prompt"]
    assert "Ticket Conversation History" in prompt_arg
    assert "VPN keeps dropping" in prompt_arg
    assert "Checked VPN config" in prompt_arg
    assert "(client)" in prompt_arg
    assert "(technician)" in prompt_arg


@pytest.mark.asyncio
async def test_generate_empty_notes(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """POST /generate with empty notes list is backward-compatible (200)."""
    mock_rag, mock_llm, mock_ms = create_mock_services()
    apply_services(test_app, mock_rag, mock_llm, mock_ms)

    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "ticket_description": "Test",
        "notes": [],
    })
    assert response.status_code == 200

    prompt_arg = mock_llm.generate.call_args.kwargs["prompt"]
    assert "Ticket Conversation History" not in prompt_arg


@pytest.mark.asyncio
async def test_generate_notes_validation_max_length(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """Note text exceeding 4000 chars returns 422."""
    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "notes": [{"text": "x" * 4001}],
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_notes_validation_max_count(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """More than 50 notes returns 422."""
    notes = [{"text": f"Note {i}"} for i in range(51)]
    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "notes": notes,
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_notes_type_validation(
    test_app: FastAPI, client: AsyncClient,
) -> None:
    """Invalid note type value returns 422."""
    response = await client.post("/generate", json={
        "ticket_subject": "Test",
        "notes": [{"text": "Hello", "type": "invalid_type"}],
    })
    assert response.status_code == 422


class TestFormatNotesSection:
    """Unit tests for _format_notes_section()."""

    def _request(self, notes: list[dict[str, str]] | None = None) -> GenerateRequest:
        return GenerateRequest(
            ticket_subject="Test",
            notes=[NoteItem(**n) for n in (notes or [])],
        )

    def test_empty_notes_returns_empty(self) -> None:
        assert _format_notes_section(self._request()) == ""

    def test_notes_in_chronological_order(self) -> None:
        """Notes should be reversed to oldest-first."""
        notes = [
            {"author": "B", "text": "Second", "date": "2026-03-02"},
            {"author": "A", "text": "First", "date": "2026-03-01"},
        ]
        result = _format_notes_section(self._request(notes))
        # "First" (originally last) should come before "Second" after reversal
        assert result.index("First") < result.index("Second")

    def test_caps_at_10_notes(self) -> None:
        """Only the 10 most recent notes should be included.

        Input is newest-first (as sent by the extension). After reversal
        to chronological order and taking the last 10, the 5 oldest
        notes (indices 10-14 in the original newest-first list) are dropped.
        """
        # Newest-first: Note 0 is most recent, Note 14 is oldest
        notes = [{"author": f"Author {i}", "text": f"Note {i}"} for i in range(15)]
        result = _format_notes_section(self._request(notes))
        # After reversal: [Note 14, Note 13, ..., Note 0] (oldest first)
        # Last 10: [Note 9, Note 8, ..., Note 0]
        # So Note 14 (oldest) should be excluded, Note 0 (newest) included
        assert "Note 14" not in result
        assert "Note 0" in result
        # Verify exactly 10 notes present (count "(client):" patterns)
        assert result.count("(client):\n") == 10

    def test_type_labels(self) -> None:
        notes = [
            {"text": "a", "type": "client"},
            {"text": "b", "type": "tech_visible"},
            {"text": "c", "type": "tech_internal"},
        ]
        result = _format_notes_section(self._request(notes))
        assert "(client)" in result
        assert "(technician)" in result
        assert "(internal note)" in result
