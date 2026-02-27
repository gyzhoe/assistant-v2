from pydantic import BaseModel


class ContextDoc(BaseModel):
    content: str
    source: str  # "kb" | "ticket"
    score: float
    metadata: dict[str, object]


class GenerateResponse(BaseModel):
    reply: str
    model_used: str
    context_docs: list[ContextDoc]
    latency_ms: int


class IngestUploadResponse(BaseModel):
    filename: str
    collection: str
    chunks_ingested: int
    processing_time_ms: int
    warning: str | None = None  # e.g., "No text content extracted"


class IngestUrlResponse(BaseModel):
    url: str
    collection: str
    chunks_ingested: int
    processing_time_ms: int
    title: str | None = None
    warning: str | None = None
