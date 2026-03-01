"""Extended tests for the IngestionPipeline — status, clear_all, batching, edge cases.

Complements test_ingestion.py which covers file routing and loader integration.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

from ingestion.pipeline import (
    _BATCH_SIZE,
    KB_COLLECTION,
    TICKET_COLLECTION,
    IngestionPipeline,
)


def _make_pipeline(
    embed_fn: object | None = None,
) -> tuple[IngestionPipeline, MagicMock]:
    """Create a pipeline with mock ChromaDB client."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    fn = embed_fn if embed_fn is not None else lambda _text: [0.1] * 768
    pipeline = IngestionPipeline(chroma_client=mock_client, embed_fn=fn)
    return pipeline, mock_client


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------


def test_status_returns_collection_counts() -> None:
    """status() should return a dict of collection names to document counts."""
    pipeline, mock_client = _make_pipeline()

    col1 = MagicMock()
    col1.name = "whd_tickets"
    col1.count.return_value = 42
    col2 = MagicMock()
    col2.name = "kb_articles"
    col2.count.return_value = 18
    mock_client.list_collections.return_value = [col1, col2]

    result = pipeline.status()
    assert result == {"whd_tickets": 42, "kb_articles": 18}


def test_status_returns_empty_on_exception() -> None:
    """status() should return {} when list_collections raises."""
    pipeline, mock_client = _make_pipeline()
    mock_client.list_collections.side_effect = RuntimeError("DB error")

    result = pipeline.status()
    assert result == {}


# ---------------------------------------------------------------------------
# clear_all()
# ---------------------------------------------------------------------------


def test_clear_all_deletes_collections() -> None:
    """clear_all() should delete every collection."""
    pipeline, mock_client = _make_pipeline()

    col1 = MagicMock()
    col1.name = "whd_tickets"
    col2 = MagicMock()
    col2.name = "kb_articles"
    mock_client.list_collections.return_value = [col1, col2]

    pipeline.clear_all()

    mock_client.delete_collection.assert_any_call("whd_tickets")
    mock_client.delete_collection.assert_any_call("kb_articles")
    assert mock_client.delete_collection.call_count == 2


# ---------------------------------------------------------------------------
# Collection creation per format
# ---------------------------------------------------------------------------


def test_ingest_tickets_creates_whd_collection(tmp_path: Path) -> None:
    """ingest_tickets should create/get the whd_tickets collection."""
    data = [{"id": "1", "subject": "Test", "description": "Desc"}]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    pipeline, mock_client = _make_pipeline()
    pipeline.ingest_tickets(f)

    mock_client.get_or_create_collection.assert_called_once()
    assert mock_client.get_or_create_collection.call_args.kwargs["name"] == TICKET_COLLECTION


def test_ingest_kb_html_creates_kb_collection(tmp_path: Path) -> None:
    """ingest_kb_html should create/get the kb_articles collection."""
    html_dir = tmp_path / "kb"
    html_dir.mkdir()
    (html_dir / "article.html").write_text("<html><body><p>Content</p></body></html>")

    pipeline, mock_client = _make_pipeline()
    pipeline.ingest_kb_html(html_dir)

    mock_client.get_or_create_collection.assert_called_once()
    assert mock_client.get_or_create_collection.call_args.kwargs["name"] == KB_COLLECTION


def test_ingest_kb_pdf_creates_kb_collection(tmp_path: Path) -> None:
    """ingest_kb_pdf should create/get the kb_articles collection."""
    from pypdf import PdfWriter

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with (pdf_dir / "doc.pdf").open("wb") as fp:
        writer.write(fp)

    pipeline, mock_client = _make_pipeline()
    pipeline.ingest_kb_pdf(pdf_dir)

    mock_client.get_or_create_collection.assert_called_once()
    assert mock_client.get_or_create_collection.call_args.kwargs["name"] == KB_COLLECTION


# ---------------------------------------------------------------------------
# upsert_stream batching
# ---------------------------------------------------------------------------


def test_upsert_stream_batches_at_batch_size() -> None:
    """upsert_stream with 75 items should produce 2 upsert calls (50 + 25)."""
    pipeline, mock_client = _make_pipeline()
    mock_collection = mock_client.get_or_create_collection.return_value

    def make_stream(n: int) -> Iterator[tuple[str, str, dict[str, str]]]:
        for i in range(n):
            yield (f"id-{i}", f"text-{i}", {"source": "test"})

    total = pipeline.upsert_stream(mock_collection, make_stream(75))

    assert total == 75
    assert mock_collection.upsert.call_count == 2
    # First batch should have 50 items, second should have 25
    first_call_ids = mock_collection.upsert.call_args_list[0].kwargs["ids"]
    second_call_ids = mock_collection.upsert.call_args_list[1].kwargs["ids"]
    assert len(first_call_ids) == _BATCH_SIZE
    assert len(second_call_ids) == 25


def test_upsert_stream_empty_yields_zero() -> None:
    """upsert_stream with an empty iterator should return 0 and never call upsert."""
    pipeline, mock_client = _make_pipeline()
    mock_collection = mock_client.get_or_create_collection.return_value

    total = pipeline.upsert_stream(mock_collection, iter([]))

    assert total == 0
    mock_collection.upsert.assert_not_called()
