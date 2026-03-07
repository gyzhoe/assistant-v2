"""Tests for ChromaDB cold-start warm-up."""

import logging
from unittest.mock import MagicMock

import pytest

from app.main import warmup_chromadb


def test_warmup_logs_collection_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warm-up should log document counts for existing collections."""
    mock_col = MagicMock()
    mock_col.count.return_value = 42

    mock_chroma = MagicMock()
    mock_chroma.get_collection.return_value = mock_col

    with caplog.at_level(logging.INFO, logger="app.main"):
        warmup_chromadb(mock_chroma)

    log_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "whd_tickets has 42 documents" in log_messages
    assert "kb_articles has 42 documents" in log_messages
    assert mock_chroma.get_collection.call_count == 2


def test_warmup_handles_missing_collections(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warm-up should not crash when collections don't exist yet."""
    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = Exception("Collection not found")

    with caplog.at_level(logging.DEBUG, logger="app.main"):
        warmup_chromadb(mock_chroma)

    log_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "not found" in log_messages
    assert mock_chroma.get_collection.call_count == 2


def test_warmup_partial_collections(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warm-up handles one collection existing and the other missing."""
    mock_col = MagicMock()
    mock_col.count.return_value = 10

    mock_chroma = MagicMock()
    mock_chroma.get_collection.side_effect = [
        mock_col,  # kb_articles found
        Exception("Collection not found"),  # whd_tickets missing
    ]

    with caplog.at_level(logging.DEBUG, logger="app.main"):
        warmup_chromadb(mock_chroma)

    log_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "kb_articles has 10 documents" in log_messages
    assert "whd_tickets not found" in log_messages
