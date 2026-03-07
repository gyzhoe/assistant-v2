import re
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# Enterprise input limits — prevents oversized payloads reaching the LLM server
# and mitigates prompt injection via extremely long ticket content.
_SUBJECT_MAX = 500
_DESCRIPTION_MAX = 16_000   # ~4k tokens — generous for real tickets
_SHORT_FIELD_MAX = 200
_MODEL_MAX = 100

# custom_fields limits
_CF_MAX_KEYS = 10
_CF_MAX_KEY_LEN = 100
_CF_MAX_VAL_LEN = 500
# Match control chars < 0x20 except \n (0x0a) and \t (0x09)
_CF_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


_NOTE_TEXT_MAX = 4000
_NOTE_SHORT_MAX = 200
_NOTE_ID_MAX = 50
_NOTE_MAX_COUNT = 50


class NoteItem(BaseModel):
    author: str = Field(default="", max_length=_NOTE_SHORT_MAX)
    text: str = Field(default="", max_length=_NOTE_TEXT_MAX)
    type: Literal["client", "tech_visible", "tech_internal"] = "client"
    date: str = Field(default="", max_length=_NOTE_ID_MAX)
    note_id: str = Field(default="", max_length=_NOTE_ID_MAX)
    time_spent: str = Field(default="", max_length=_NOTE_ID_MAX)


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
    model: str = Field(default="qwen3.5:9b", max_length=_MODEL_MAX, description="LLM model to use")
    max_context_docs: int = Field(default=5, ge=1, le=20)
    stream: bool = Field(default=False)
    custom_fields: dict[str, str] = Field(
        default_factory=dict, description="WHD custom fields (e.g., Network Connection Label, Building, Room, Mac address)"
    )
    include_web_context: bool = Field(default=True, description="Include Microsoft Learn search results")
    prompt_suffix: str = Field(
        default="", max_length=2000, description="Custom instructions appended to the prompt"
    )
    pinned_article_ids: list[str] = Field(
        default_factory=list, max_length=10, description="KB article IDs to inject as pinned context"
    )
    notes: list[NoteItem] = Field(
        default_factory=list, description="Ticket conversation notes"
    )

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: list[NoteItem]) -> list[NoteItem]:
        if len(v) > _NOTE_MAX_COUNT:
            msg = f"Maximum {_NOTE_MAX_COUNT} notes allowed"
            raise ValueError(msg)
        return v

    @field_validator("pinned_article_ids")
    @classmethod
    def validate_pinned_article_ids(cls, v: list[str]) -> list[str]:
        for item in v:
            if len(item) > _SHORT_FIELD_MAX:
                msg = f"Each pinned article ID must be at most {_SHORT_FIELD_MAX} characters"
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_custom_fields(self) -> "GenerateRequest":
        """Enforce limits on custom_fields: max 10 keys, key/value
        lengths, and strip control characters (except newline/tab)."""
        cf = self.custom_fields
        if len(cf) > _CF_MAX_KEYS:
            msg = f"custom_fields: maximum {_CF_MAX_KEYS} keys allowed"
            raise ValueError(msg)

        cleaned: dict[str, str] = {}
        for key, val in cf.items():
            if len(key) > _CF_MAX_KEY_LEN:
                msg = (
                    f"custom_fields key too long "
                    f"({len(key)} > {_CF_MAX_KEY_LEN}): "
                    f"{key[:30]}..."
                )
                raise ValueError(msg)
            if len(val) > _CF_MAX_VAL_LEN:
                msg = (
                    f"custom_fields value too long for "
                    f"'{key[:30]}' "
                    f"({len(val)} > {_CF_MAX_VAL_LEN})"
                )
                raise ValueError(msg)
            cleaned[_CF_CONTROL_RE.sub("", key)] = (
                _CF_CONTROL_RE.sub("", val)
            )

        self.custom_fields = cleaned
        return self


class IngestUrlRequest(BaseModel):
    url: HttpUrl = Field(description="URL to fetch and ingest")


def _validate_tag_list(v: list[str]) -> list[str]:
    """Validate and normalize a list of tags.

    Strips whitespace, drops empty strings, rejects commas (used as
    delimiter in ChromaDB metadata) and enforces length limits.
    """
    cleaned: list[str] = []
    for tag in v:
        tag = tag.strip()
        if not tag:
            continue
        if "," in tag:
            msg = "Tags must not contain commas"
            raise ValueError(msg)
        if len(tag) > 100:
            msg = "Each tag must be at most 100 characters"
            raise ValueError(msg)
        cleaned.append(tag)
    if len(cleaned) > 20:
        msg = "Maximum 20 tags allowed"
        raise ValueError(msg)
    return cleaned


class ArticleRequest(BaseModel):
    """Shared model for creating and updating KB articles."""

    title: str = Field(min_length=1, max_length=200, description="Article title")
    content: str = Field(min_length=1, max_length=100_000, description="Markdown content")
    tags: list[str] = Field(default_factory=list, description="Article tags (max 20)")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _validate_tag_list(v)


# Backwards-compatible aliases
CreateArticleRequest = ArticleRequest
UpdateArticleRequest = ArticleRequest


class UpdateTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, description="New tags for the article")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return _validate_tag_list(v)


class FeedbackRequest(BaseModel):
    ticket_subject: str = Field(..., max_length=500)
    ticket_description: str = Field(..., max_length=16000)
    category: str = Field("", max_length=200)
    reply: str = Field(..., max_length=4000)
    rating: Literal["good", "bad"]


class SwitchModelRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=100)


class DownloadModelsRequest(BaseModel):
    models: list[str] = Field(default_factory=list, description="GGUF filenames to download (empty = all missing)")
