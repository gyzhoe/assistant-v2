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
    default_model: str = "llama3.2:3b"
    version: str = "1.4.0"
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

    # Microsoft Learn live search at generation time
    microsoft_docs_enabled: bool = True

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
