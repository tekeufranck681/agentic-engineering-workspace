"""Configuration for the isolated execution sandbox (E2B)."""

from dotenv import find_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class SandboxConfigError(Exception):
    """Settings are missing; no sandbox was created."""


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="E2B_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    api_key: SecretStr | None = None
    """E2B API key from the E2B dashboard. Local .env only."""

    template: str | None = None
    """Sandbox template id; None uses E2B's default base image."""

    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    """Hard lifetime: E2B shuts the sandbox down after this even if we crash."""

    command_timeout_seconds: int = Field(default=120, ge=5, le=1800)

    @classmethod
    def from_env(cls) -> "SandboxSettings":
        try:
            settings = cls()
        except Exception as exc:
            raise SandboxConfigError(f"invalid sandbox configuration: {exc}") from exc
        if not settings.api_key or not settings.api_key.get_secret_value().strip():
            raise SandboxConfigError("E2B_API_KEY is not set: copy it from the E2B dashboard into the local .env only")
        return settings

    def key(self) -> str:
        assert self.api_key is not None
        return self.api_key.get_secret_value().strip()
