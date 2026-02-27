from pydantic import BaseModel, Field, HttpUrl

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
    model: str = Field(default="qwen2.5:14b", max_length=_MODEL_MAX, description="Ollama model to use")
    max_context_docs: int = Field(default=5, ge=1, le=20)
    stream: bool = Field(default=False)
    custom_fields: dict[str, str] = Field(
        default_factory=dict, description="WHD custom fields (e.g., Network Connection Label, Building, Room, Mac address)"
    )
    include_web_context: bool = Field(default=True, description="Include Microsoft Learn search results")
    prompt_suffix: str = Field(
        default="", max_length=2000, description="Custom instructions appended to the prompt"
    )


class IngestUrlRequest(BaseModel):
    url: HttpUrl = Field(description="URL to fetch and ingest")


class CreateArticleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="Article title")
    content: str = Field(min_length=1, max_length=100_000, description="Markdown content")
