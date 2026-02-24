from pydantic import BaseModel, Field

# Enterprise input limits — prevents oversized payloads reaching Ollama
# and mitigates prompt injection via extremely long ticket content.
_SUBJECT_MAX = 500
_DESCRIPTION_MAX = 16_000   # ~4k tokens — generous for real tickets
_SHORT_FIELD_MAX = 200
_MODEL_MAX = 100


class GenerateRequest(BaseModel):
    ticket_subject: str = Field(
        default="", max_length=_SUBJECT_MAX, description="Ticket subject line"
    )
    ticket_description: str = Field(
        default="", max_length=_DESCRIPTION_MAX, description="Full problem description"
    )
    requester_name: str = Field(default="", max_length=_SHORT_FIELD_MAX, description="Requester's name")
    category: str = Field(default="", max_length=_SHORT_FIELD_MAX, description="WHD ticket category")
    status: str = Field(default="", max_length=_SHORT_FIELD_MAX, description="WHD ticket status")
    model: str = Field(default="llama3.2:3b", max_length=_MODEL_MAX, description="Ollama model to use")
    max_context_docs: int = Field(default=5, ge=1, le=20)
    stream: bool = Field(default=False)
    prompt_suffix: str = Field(
        default="", max_length=2000, description="Custom instructions appended to the prompt"
    )
