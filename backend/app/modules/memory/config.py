"""Configuration for the H-MEM sidecar connection (HMEM_* variables).

The sidecar holds no credentials and the backend sends none: it is an
internal service, published on localhost or the compose network only.
"""

from dotenv import find_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BASE_URL = "http://127.0.0.1:8099"

# Same .env discovery as the other settings: walk upward from the working directory.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class MemorySettings(BaseSettings):
    """Where the hmem-service runs and how capabilities recall from it."""

    model_config = SettingsConfigDict(
        env_prefix="HMEM_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    base_url: str = DEFAULT_BASE_URL
    """hmem-service URL as seen from the backend (compose: http://hmem:8099)."""

    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    recall_top_n: int = Field(default=5, ge=1, le=20)
    """Most memories a capability prompt receives (the H-MEM default)."""

    recall_threshold: float = Field(default=0.35, ge=0, le=1)
    """Minimum final H-MEM score, after the confidence multiplier (the H-MEM default)."""
