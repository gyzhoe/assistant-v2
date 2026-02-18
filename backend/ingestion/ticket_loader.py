"""
WHD ticket loader — parses JSON and CSV ticket exports from SolarWinds Web Help Desk.

Expected JSON format (array of ticket objects):
  [
    {
      "id": "1042",
      "subject": "Cannot access network drive",
      "description": "User reports...",
      "resolution": "Remapped drive via Group Policy.",
      "category": "Network",
      "status": "Closed",
      "resolved_date": "2024-01-15"
    },
    ...
  ]

CSV format: header row with the same field names (case-insensitive).
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator


def _content_id(content: str) -> str:
    """Stable SHA-256 document ID — re-ingesting same content is idempotent."""
    return hashlib.sha256(content[:200].encode()).hexdigest()


def load_tickets_json(path: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """
    Yield (doc_id, text, metadata) tuples from a WHD JSON export.
    'text' combines subject + description + resolution for embedding.
    """
    with path.open(encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON array, got {type(records).__name__}")

    for rec in records:
        if not isinstance(rec, dict):
            continue

        subject = str(rec.get("subject", "")).strip()
        description = str(rec.get("description", "")).strip()
        resolution = str(rec.get("resolution", "")).strip()

        if not subject and not description:
            continue

        text = "\n\n".join(part for part in [subject, description, resolution] if part)
        doc_id = _content_id(text)
        metadata: dict[str, str] = {
            "ticket_id": str(rec.get("id", "")),
            "subject": subject[:200],
            "category": str(rec.get("category", "")),
            "status": str(rec.get("status", "")),
            "resolved_date": str(rec.get("resolved_date", "")),
        }
        yield doc_id, text, metadata


def load_tickets_csv(path: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """
    Yield (doc_id, text, metadata) tuples from a WHD CSV export.
    Header row field names are normalized to lowercase.
    """
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            norm = {k.lower().strip(): v.strip() for k, v in row.items() if k}

            subject = norm.get("subject", "")
            description = norm.get("description", "")
            resolution = norm.get("resolution", "")

            if not subject and not description:
                continue

            text = "\n\n".join(part for part in [subject, description, resolution] if part)
            doc_id = _content_id(text)
            metadata: dict[str, str] = {
                "ticket_id": norm.get("id", ""),
                "subject": subject[:200],
                "category": norm.get("category", ""),
                "status": norm.get("status", ""),
                "resolved_date": norm.get("resolved_date", ""),
            }
            yield doc_id, text, metadata


def load_tickets(path: Path) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Auto-detect format based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        yield from load_tickets_json(path)
    elif suffix == ".csv":
        yield from load_tickets_csv(path)
    else:
        raise ValueError(f"Unsupported ticket export format: {suffix} (use .json or .csv)")
