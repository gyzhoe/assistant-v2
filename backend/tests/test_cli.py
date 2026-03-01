"""Tests for the ingestion CLI (Typer commands via CliRunner).

Covers all 5 CLI commands: ingest-tickets, ingest-kb-html, ingest-kb-pdf, status, clear.
Each test mocks _make_pipeline to avoid real ChromaDB/Ollama dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ingestion.cli import app

runner = CliRunner()


def _mock_pipeline(**overrides: object) -> MagicMock:
    """Create a mock IngestionPipeline with sensible defaults."""
    mock = MagicMock()
    mock.ingest_tickets.return_value = overrides.get("ingest_tickets", 5)
    mock.ingest_kb_html.return_value = overrides.get("ingest_kb_html", 3)
    mock.ingest_kb_pdf.return_value = overrides.get("ingest_kb_pdf", 2)
    mock.status.return_value = overrides.get("status", {"whd_tickets": 10, "kb_articles": 5})
    mock.clear_all.return_value = None
    return mock


# ---------------------------------------------------------------------------
# ingest-tickets
# ---------------------------------------------------------------------------


def test_ingest_tickets_success_json(tmp_path: Path) -> None:
    """ingest-tickets with a valid JSON file should report success."""
    data = [{"id": "1", "subject": "Test", "description": "Desc"}]
    f = tmp_path / "export.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    mock = _mock_pipeline(ingest_tickets=3)
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["ingest-tickets", str(f)])

    assert result.exit_code == 0
    assert "3 ticket(s)" in result.output
    mock.ingest_tickets.assert_called_once_with(f)


def test_ingest_tickets_file_not_found() -> None:
    """ingest-tickets with a non-existent file should fail with exit code 1."""
    result = runner.invoke(app, ["ingest-tickets", "/nonexistent/path/export.json"])
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_ingest_tickets_csv_variant(tmp_path: Path) -> None:
    """ingest-tickets should accept CSV files."""
    csv_content = "id,subject,description\n1,Test,Desc\n"
    f = tmp_path / "export.csv"
    f.write_text(csv_content, encoding="utf-8")

    mock = _mock_pipeline(ingest_tickets=1)
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["ingest-tickets", str(f)])

    assert result.exit_code == 0
    assert "1 ticket(s)" in result.output


# ---------------------------------------------------------------------------
# ingest-kb-html
# ---------------------------------------------------------------------------


def test_ingest_kb_html_success(tmp_path: Path) -> None:
    """ingest-kb-html with a valid directory should report success."""
    (tmp_path / "article.html").write_text("<html><body>KB</body></html>")

    mock = _mock_pipeline(ingest_kb_html=7)
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["ingest-kb-html", str(tmp_path)])

    assert result.exit_code == 0
    assert "7 chunk(s)" in result.output
    mock.ingest_kb_html.assert_called_once_with(tmp_path)


def test_ingest_kb_html_not_a_directory(tmp_path: Path) -> None:
    """ingest-kb-html with a file (not directory) should fail."""
    f = tmp_path / "file.txt"
    f.write_text("not a dir")

    result = runner.invoke(app, ["ingest-kb-html", str(f)])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


# ---------------------------------------------------------------------------
# ingest-kb-pdf
# ---------------------------------------------------------------------------


def test_ingest_kb_pdf_success(tmp_path: Path) -> None:
    """ingest-kb-pdf with a valid directory should report success."""
    (tmp_path / "doc.pdf").write_bytes(b"fake pdf content")

    mock = _mock_pipeline(ingest_kb_pdf=4)
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["ingest-kb-pdf", str(tmp_path)])

    assert result.exit_code == 0
    assert "4 chunk(s)" in result.output
    mock.ingest_kb_pdf.assert_called_once_with(tmp_path)


def test_ingest_kb_pdf_not_a_directory(tmp_path: Path) -> None:
    """ingest-kb-pdf with a file (not directory) should fail."""
    f = tmp_path / "file.txt"
    f.write_text("not a dir")

    result = runner.invoke(app, ["ingest-kb-pdf", str(f)])
    assert result.exit_code == 1
    assert "Not a directory" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_with_collections() -> None:
    """status should display collection names and document counts."""
    mock = _mock_pipeline(status={"whd_tickets": 42, "kb_articles": 18})
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "whd_tickets" in result.output
    assert "42" in result.output
    assert "kb_articles" in result.output
    assert "18" in result.output
    assert "TOTAL" in result.output
    assert "60" in result.output


def test_status_no_collections() -> None:
    """status with no collections should show a helpful message."""
    mock = _mock_pipeline(status={})
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "No collections found" in result.output


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_without_confirm() -> None:
    """clear without --confirm should abort with exit code 1."""
    result = runner.invoke(app, ["clear"])
    assert result.exit_code == 1
    assert "ABORT" in result.output


def test_clear_with_confirm() -> None:
    """clear --confirm should call clear_all and succeed."""
    mock = _mock_pipeline()
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["clear", "--confirm"])

    assert result.exit_code == 0
    assert "cleared" in result.output
    mock.clear_all.assert_called_once()


# ---------------------------------------------------------------------------
# Pipeline exception propagation
# ---------------------------------------------------------------------------


def test_pipeline_exception_propagates(tmp_path: Path) -> None:
    """Exceptions raised by the pipeline should propagate through the CLI."""
    data = [{"id": "1", "subject": "Test", "description": "Desc"}]
    f = tmp_path / "export.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    mock = _mock_pipeline()
    mock.ingest_tickets.side_effect = RuntimeError("ChromaDB connection failed")
    with patch("ingestion.cli._make_pipeline", return_value=mock):
        result = runner.invoke(app, ["ingest-tickets", str(f)])

    assert result.exit_code != 0
