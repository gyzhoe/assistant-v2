"""Tests for the ingestion pipeline — ticket loader and KB loader."""

import json
from pathlib import Path

import pytest

from ingestion.ticket_loader import load_tickets_json, load_tickets_csv, load_tickets


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
