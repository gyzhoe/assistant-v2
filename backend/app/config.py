import warnings
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434"
    chroma_path: str = "./chroma_data"
    cors_origin: str = "chrome-extension://placeholder"
    default_model: str = "qwen2.5:14b"
    version: str = "1.8.0"
    prompt_template_path: str | None = None

    # Enterprise security
    # Set API_TOKEN in .env to a long random secret (e.g. `openssl rand -hex 32`).
    # The extension must send this in the X-Extension-Token header.
    # Leave empty ("") in dev to disable token auth.
    api_token: str = ""

    # Rate limiting: max /generate calls per client IP per minute
    rate_limit_per_minute: int = 20

    # Request body size limit in bytes (default 64 KB)
    max_request_bytes: int = 65_536

    # Max upload file size in bytes (default 50 MB)
    max_upload_bytes: int = 52_428_800

    # LLM sampling parameters — tuned for factual, grounded helpdesk replies
    llm_temperature: float = 0.3
    llm_top_p: float = 0.9
    llm_top_k: int = 40
    llm_repeat_penalty: float = 1.1
    llm_num_predict: int = 300

    # RAG minimum similarity threshold — docs below this score are noise
    rag_min_similarity: float = 0.35

    # Microsoft Learn live search at generation time
    microsoft_docs_enabled: bool = True

    # Optional environment context injected into the LLM prompt.
    # Set this in .env to describe your network/environment for better replies.
    # Example: "Managed corporate network. Devices use certificate-based auth."
    # Leave empty to omit the ENVIRONMENT section from the prompt.
    environment_context: str = ""

    @model_validator(mode="after")
    def reject_wildcard_cors_with_token(self) -> Self:
        """Reject CORS_ORIGIN=* when API_TOKEN is set.

        Combining a wildcard CORS origin with token-based authentication is a
        security misconfiguration: any website can issue credentialed requests
        against the backend, making the token the only line of defence.  In
        production (api_token non-empty) a specific extension origin must be
        provided instead.
        """
        if self.api_token and self.cors_origin == "*":
            raise ValueError(
                "CORS_ORIGIN='*' is not allowed when API_TOKEN is set. "
                "Set CORS_ORIGIN to your extension origin "
                "(e.g. chrome-extension://<ID>) to secure the backend."
            )
        if not self.api_token and self.cors_origin == "*":
            warnings.warn(
                "CORS_ORIGIN='*' is set with no API_TOKEN — acceptable for "
                "local development only. Never use this configuration in "
                "production.",
                stacklevel=2,
            )
        return self


settings = Settings()
