"""Tests for the dynamic few-shot example retrieval in generate.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.prompt_service import (
    _HARDCODED_EXAMPLES,
    _MIN_FEWSHOT_SIMILARITY,
    _build_examples_section,
    _get_dynamic_examples,
)

FAKE_EMBEDDING: list[float] = [0.1] * 768


def _mock_chroma_with_rated(
    metadatas: list[dict[str, str]],
    distances: list[float],
    documents: list[str] | None = None,
) -> MagicMock:
    """Build a mock ChromaDB client with a rated_replies collection."""
    mock_client = MagicMock()
    mock_col = MagicMock()
    mock_client.get_collection.return_value = mock_col
    mock_col.count.return_value = len(metadatas)

    result: dict[str, Any] = {
        "metadatas": [metadatas],
        "distances": [distances],
        "documents": [documents or [""] * len(metadatas)],
    }
    mock_col.query.return_value = result
    return mock_client


@pytest.mark.asyncio
async def test_returns_examples_above_threshold() -> None:
    # Distance 0.3 => score 0.7 (above 0.65 threshold)
    client = _mock_chroma_with_rated(
        metadatas=[{"rating": "good", "category": "NET", "reply": "Try restarting."}],
        distances=[0.3],
        documents=["VPN not connecting\nUser cannot connect"],
    )
    examples = await _get_dynamic_examples(client, "test query", "NET", FAKE_EMBEDDING)
    assert len(examples) == 1
    assert examples[0]["ticket_subject"] == "VPN not connecting"
    assert examples[0]["reply"] == "Try restarting."


@pytest.mark.asyncio
async def test_filters_below_threshold() -> None:
    # Distance 0.5 => score 0.5 (below 0.65 threshold)
    client = _mock_chroma_with_rated(
        metadatas=[{"rating": "good", "category": "NET", "reply": "Try restarting."}],
        distances=[0.5],
        documents=["VPN issue\nDetails"],
    )
    examples = await _get_dynamic_examples(client, "test query", "NET", FAKE_EMBEDDING)
    assert len(examples) == 0


@pytest.mark.asyncio
async def test_returns_empty_for_empty_collection() -> None:
    mock_client = MagicMock()
    mock_col = MagicMock()
    mock_client.get_collection.return_value = mock_col
    mock_col.count.return_value = 0

    examples = await _get_dynamic_examples(mock_client, "test query", "NET", FAKE_EMBEDDING)
    assert examples == []


@pytest.mark.asyncio
async def test_returns_empty_on_missing_collection() -> None:
    mock_client = MagicMock()
    mock_client.get_collection.side_effect = ValueError("Collection not found")

    examples = await _get_dynamic_examples(mock_client, "test query", "NET", FAKE_EMBEDDING)
    assert examples == []


@pytest.mark.asyncio
async def test_extracts_subject_from_document_first_line() -> None:
    client = _mock_chroma_with_rated(
        metadatas=[{"rating": "good", "category": "EMAIL", "reply": "Check settings."}],
        distances=[0.2],
        documents=["Outlook keeps crashing\nIt crashes on startup every time."],
    )
    examples = await _get_dynamic_examples(client, "test query", "EMAIL", FAKE_EMBEDDING)
    assert examples[0]["ticket_subject"] == "Outlook keeps crashing"


@pytest.mark.asyncio
async def test_skips_examples_with_empty_reply() -> None:
    client = _mock_chroma_with_rated(
        metadatas=[{"rating": "good", "category": "NET", "reply": ""}],
        distances=[0.2],
        documents=["Subject\nDescription"],
    )
    examples = await _get_dynamic_examples(client, "test query", "NET", FAKE_EMBEDDING)
    assert len(examples) == 0


@pytest.mark.asyncio
async def test_falls_back_without_category_filter() -> None:
    """When category is empty, should query without category filter."""
    client = _mock_chroma_with_rated(
        metadatas=[{"rating": "good", "category": "", "reply": "Generic fix."}],
        distances=[0.2],
        documents=["Some issue\nDetails"],
    )
    examples = await _get_dynamic_examples(client, "test query", "", FAKE_EMBEDDING)
    assert len(examples) == 1
    # Verify query was called without $and category filter
    col = client.get_collection.return_value
    call_kwargs = col.query.call_args
    where = call_kwargs.kwargs.get("where") or call_kwargs[1].get("where")
    assert "$and" not in where
    assert where == {"rating": {"$eq": "good"}}


def test_build_examples_section_uses_hardcoded_when_empty() -> None:
    result = _build_examples_section(None)
    assert result == _HARDCODED_EXAMPLES

    result2 = _build_examples_section([])
    assert result2 == _HARDCODED_EXAMPLES


def test_build_examples_section_uses_dynamic_when_available() -> None:
    examples = [
        {"ticket_subject": "VPN issue", "reply": "Clear credentials."},
        {"ticket_subject": "Outlook crash", "reply": "Run safe mode."},
    ]
    result = _build_examples_section(examples)
    assert "real validated reply" in result
    assert "VPN issue" in result
    assert "Clear credentials." in result
    assert "Outlook crash" in result
    assert "Run safe mode." in result
    # Should NOT contain hardcoded examples
    assert "control keymgr.dll" not in result


def test_min_fewshot_similarity_is_reasonable() -> None:
    """Threshold should be between 0.5 and 0.8 for practical use."""
    assert 0.5 <= _MIN_FEWSHOT_SIMILARITY <= 0.8
