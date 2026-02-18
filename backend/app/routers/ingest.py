from fastapi import APIRouter

router = APIRouter(tags=["ingest"])


@router.post("/ingest")
async def ingest_status() -> dict[str, str]:
    """Placeholder — ingestion is handled by the CLI (ingestion/cli.py)."""
    return {"message": "Use the CLI: python -m ingestion.cli --help"}
