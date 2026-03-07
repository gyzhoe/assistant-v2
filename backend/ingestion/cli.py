"""
Ingestion CLI — AI Helpdesk Assistant

Usage:
  python -m ingestion.cli ingest-tickets export.json
  python -m ingestion.cli ingest-kb-html ./kb_articles/
  python -m ingestion.cli ingest-kb-pdf ./kb_pdfs/
  python -m ingestion.cli status
  python -m ingestion.cli clear --confirm
"""

from pathlib import Path

import typer

from ingestion.pipeline import IngestionPipeline

app = typer.Typer(
    name="ingestion",
    help="Ingest WHD ticket exports and KB articles into ChromaDB.",
    add_completion=False,
)


def _make_pipeline() -> IngestionPipeline:
    import chromadb
    import httpx

    from app.config import settings
    from app.services.embed_service import EmbedService

    chroma = chromadb.PersistentClient(path=settings.chroma_path)
    sync_client = httpx.Client(
        base_url=settings.embed_base_url, timeout=60.0,
    )
    embed_svc = EmbedService(client=sync_client)
    return IngestionPipeline(chroma_client=chroma, embed_fn=embed_svc.embed_fn)


@app.command()
def ingest_tickets(
    export_file: Path = typer.Argument(..., help="Path to WHD JSON or CSV export file"),
) -> None:
    """Import resolved WHD tickets from a JSON or CSV export."""
    if not export_file.exists():
        typer.echo(f"[ERROR] File not found: {export_file}", err=True)
        raise typer.Exit(1)

    pipeline = _make_pipeline()
    typer.echo(f"Ingesting tickets from {export_file} …")
    count = pipeline.ingest_tickets(export_file)
    typer.echo(f"[OK] Ingested {count} ticket(s).")


@app.command()
def ingest_kb_html(
    directory: Path = typer.Argument(..., help="Directory containing HTML KB articles"),
) -> None:
    """Import KB articles from a directory of HTML files."""
    if not directory.is_dir():
        typer.echo(f"[ERROR] Not a directory: {directory}", err=True)
        raise typer.Exit(1)

    pipeline = _make_pipeline()
    typer.echo(f"Ingesting KB HTML from {directory} …")
    count = pipeline.ingest_kb_html(directory)
    typer.echo(f"[OK] Ingested {count} chunk(s) from HTML articles.")


@app.command()
def ingest_kb_pdf(
    directory: Path = typer.Argument(..., help="Directory containing PDF KB articles"),
) -> None:
    """Import KB articles from a directory of PDF files."""
    if not directory.is_dir():
        typer.echo(f"[ERROR] Not a directory: {directory}", err=True)
        raise typer.Exit(1)

    pipeline = _make_pipeline()
    typer.echo(f"Ingesting KB PDF from {directory} …")
    count = pipeline.ingest_kb_pdf(directory)
    typer.echo(f"[OK] Ingested {count} chunk(s) from PDF articles.")


@app.command()
def status() -> None:
    """Show document counts for all ChromaDB collections."""
    pipeline = _make_pipeline()
    counts = pipeline.status()

    if not counts:
        typer.echo("No collections found. Run an ingest command first.")
        return

    typer.echo("\nChromaDB collection status:")
    typer.echo("─" * 35)
    for name, count in counts.items():
        typer.echo(f"  {name:<25} {count:>6} docs")
    typer.echo("─" * 35)
    typer.echo(f"  {'TOTAL':<25} {sum(counts.values()):>6} docs\n")


@app.command()
def clear(
    confirm: bool = typer.Option(False, "--confirm", help="Required to confirm deletion"),
) -> None:
    """Clear ALL ChromaDB collections. Irreversible — requires --confirm."""
    if not confirm:
        typer.echo("[ABORT] Destructive operation. Pass --confirm to proceed.", err=True)
        raise typer.Exit(1)

    pipeline = _make_pipeline()
    pipeline.clear_all()
    typer.echo("[OK] All ChromaDB collections cleared.")


if __name__ == "__main__":
    app()
