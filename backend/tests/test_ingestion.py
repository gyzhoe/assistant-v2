"""Tests for the ingestion pipeline — ticket loader and KB loader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ingestion.ticket_loader import load_tickets, load_tickets_csv, load_tickets_json

# ── Ticket loader ─────────────────────────────────────────────────────────────


def test_load_tickets_json_basic(tmp_path: Path) -> None:
    data = [
        {
            "id": "101",
            "subject": "VPN not working",
            "description": "Cannot connect to corporate VPN",
            "resolution": "Reinstalled Cisco client",
            "category": "Network",
            "status": "Closed",
            "resolved_date": "2024-01-10",
        }
    ]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    results = list(load_tickets_json(f))
    assert len(results) == 1
    doc_id, text, metadata = results[0]
    assert "VPN not working" in text
    assert "Cannot connect" in text
    assert "Reinstalled Cisco client" in text
    assert metadata["ticket_id"] == "101"
    assert metadata["category"] == "Network"


def test_load_tickets_json_skips_empty(tmp_path: Path) -> None:
    data = [{"id": "102", "subject": "", "description": ""}]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    results = list(load_tickets_json(f))
    assert len(results) == 0


def test_load_tickets_json_idempotent_ids(tmp_path: Path) -> None:
    data = [{"id": "103", "subject": "Same subject", "description": "Same desc"}]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    results1 = list(load_tickets_json(f))
    results2 = list(load_tickets_json(f))
    assert results1[0][0] == results2[0][0]  # IDs are stable


def test_load_tickets_csv_basic(tmp_path: Path) -> None:
    csv_content = "id,subject,description,resolution,category,status,resolved_date\n"
    csv_content += "200,Printer offline,Cannot print,Reset print spooler,Hardware,Closed,2024-02-01\n"

    f = tmp_path / "tickets.csv"
    f.write_text(csv_content, encoding="utf-8")

    results = list(load_tickets_csv(f))
    assert len(results) == 1
    _, text, metadata = results[0]
    assert "Printer offline" in text
    assert metadata["ticket_id"] == "200"


def test_load_tickets_auto_detect_json(tmp_path: Path) -> None:
    data = [{"id": "300", "subject": "Test", "description": "Test desc"}]
    f = tmp_path / "export.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    results = list(load_tickets(f))
    assert len(results) == 1


def test_load_tickets_auto_detect_csv(tmp_path: Path) -> None:
    csv_content = "id,subject,description\n400,Test,Test desc\n"
    f = tmp_path / "export.csv"
    f.write_text(csv_content, encoding="utf-8")
    results = list(load_tickets(f))
    assert len(results) == 1


def test_load_tickets_unsupported_format(tmp_path: Path) -> None:
    f = tmp_path / "export.xlsx"
    f.write_bytes(b"fake xlsx content")
    with pytest.raises(ValueError, match="Unsupported"):
        list(load_tickets(f))


# ── KB HTML loader ────────────────────────────────────────────────────────────


def test_load_kb_html_basic(tmp_path: Path) -> None:
    from ingestion.kb_loader import load_kb_html

    html = """<html><head><title>Password Reset Guide</title></head>
    <body>
      <h1>Password Reset Guide</h1>
      <h2>Steps</h2>
      <p>Go to the IT portal and click Reset Password.</p>
      <p>Enter your employee ID and follow the prompts.</p>
    </body></html>"""

    f = tmp_path / "password-reset.html"
    f.write_text(html, encoding="utf-8")

    results = list(load_kb_html(f))
    assert len(results) >= 1
    _, text, metadata = results[0]
    assert metadata["source_type"] == "html"
    assert "Password Reset Guide" in metadata["title"]


def test_load_kb_html_dir_empty(tmp_path: Path) -> None:
    from ingestion.kb_loader import load_kb_html_dir

    results = list(load_kb_html_dir(tmp_path))
    assert results == []


# ── Chunker utility ───────────────────────────────────────────────────────────


def test_chunker_basic() -> None:
    from app.utils.chunker import chunk_by_tokens

    text = " ".join(["word"] * 1200)
    chunks = chunk_by_tokens(text, max_tokens=500, overlap_tokens=50)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_chunker_empty() -> None:
    from app.utils.chunker import chunk_by_tokens

    assert chunk_by_tokens("") == []


def test_chunker_short_text() -> None:
    from app.utils.chunker import chunk_by_tokens

    text = "short text here"
    chunks = chunk_by_tokens(text, max_tokens=500)
    assert chunks == [text]


# ── Pipeline: ingest_file routing ────────────────────────────────────────────


def _make_pipeline(
    tmp_path: Path,
    embed_fn: object | None = None,
) -> tuple[object, MagicMock]:
    """Create an IngestionPipeline with a mock chroma client and embed_fn."""
    from ingestion.pipeline import IngestionPipeline

    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    fn = embed_fn if embed_fn is not None else lambda _text: [0.1] * 768
    pipeline = IngestionPipeline(chroma_client=mock_client, embed_fn=fn)  # type: ignore[arg-type]
    return pipeline, mock_client


def test_ingest_file_routes_json_to_tickets(tmp_path: Path) -> None:
    from ingestion.pipeline import TICKET_COLLECTION

    data = [{"id": "1", "subject": "Test", "description": "Test desc"}]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    pipeline, mock_client = _make_pipeline(tmp_path)
    collection_name, chunks = pipeline.ingest_file(f)  # type: ignore[union-attr]

    assert collection_name == TICKET_COLLECTION
    assert chunks >= 1
    mock_client.get_or_create_collection.assert_called_once()
    call_kwargs = mock_client.get_or_create_collection.call_args
    assert call_kwargs.kwargs["name"] == TICKET_COLLECTION


def test_ingest_file_routes_html_to_kb(tmp_path: Path) -> None:
    from ingestion.pipeline import KB_COLLECTION

    html = "<html><body><h1>Title</h1><p>Content here</p></body></html>"
    f = tmp_path / "article.html"
    f.write_text(html, encoding="utf-8")

    pipeline, mock_client = _make_pipeline(tmp_path)
    collection_name, chunks = pipeline.ingest_file(f)  # type: ignore[union-attr]

    assert collection_name == KB_COLLECTION
    assert chunks >= 1


def test_ingest_file_routes_pdf_to_kb(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    from ingestion.pipeline import KB_COLLECTION

    # Create a minimal valid PDF
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    f = tmp_path / "doc.pdf"
    with f.open("wb") as fp:
        writer.write(fp)

    pipeline, mock_client = _make_pipeline(tmp_path)
    collection_name, chunks = pipeline.ingest_file(f)  # type: ignore[union-attr]

    assert collection_name == KB_COLLECTION
    # Blank PDF may produce 0 chunks — that's valid behavior
    assert chunks >= 0


def test_ingest_file_raises_for_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "doc.docx"
    f.write_bytes(b"fake docx")

    pipeline, _ = _make_pipeline(tmp_path)
    with pytest.raises(ValueError, match="Unsupported file extension"):
        pipeline.ingest_file(f)  # type: ignore[union-attr]


def test_embed_fn_injection_uses_custom_fn(tmp_path: Path) -> None:
    """When embed_fn is provided, pipeline uses it instead of default _embed."""
    from ingestion.pipeline import IngestionPipeline

    calls: list[str] = []

    def custom_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.5] * 768

    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    pipeline = IngestionPipeline(chroma_client=mock_client, embed_fn=custom_embed)

    data = [{"id": "1", "subject": "Test", "description": "Desc"}]
    f = tmp_path / "tickets.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    pipeline.ingest_file(f)
    assert len(calls) >= 1, "custom embed_fn should have been called"


def test_pdf_page_limit_caps_at_500(tmp_path: Path) -> None:
    """load_kb_pdf should only process up to 500 pages."""
    from unittest.mock import patch

    from pypdf import PdfWriter

    from ingestion.kb_loader import load_kb_pdf

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    f = tmp_path / "large.pdf"
    with f.open("wb") as fp:
        writer.write(fp)

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "page text"

    mock_reader = MagicMock()
    # Create 510 pages
    mock_reader.pages = [mock_page] * 510

    with patch("ingestion.kb_loader.PdfReader", return_value=mock_reader):
        list(load_kb_pdf(f))

    # All pages' extract_text calls should total 500 (due to [:500] slice)
    assert mock_page.extract_text.call_count == 500
