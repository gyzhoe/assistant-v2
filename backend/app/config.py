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
    version: str = "1.0.0"
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


settings = Settings()
