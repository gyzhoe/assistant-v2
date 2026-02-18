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
