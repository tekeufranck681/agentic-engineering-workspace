"""Configuration for the Zetaris client.

Values come from the environment (or local .env file) and never from prompts
or code. The API key is wrapped in SecretStr so it cannot leak through reprs
or logs. Variable names match the Zetaris getting-started documentation so
teammates configure one familiar set of names.
"""

from dotenv import find_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.zetaris.errors import ZetarisConfigError

DEFAULT_REST_URL = "http://localhost:8888/api/v1.0"

# Resolve .env by walking upward from the working directory, so the module
# finds the root .env whether it runs from the repo root or from backend/.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class ZetarisSettings(BaseSettings):
    """Connection settings for the direct Zetaris REST API."""

    model_config = SettingsConfigDict(
        env_prefix="ZETARIS_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    rest_url: str = DEFAULT_REST_URL
    """API base ending in /api/v1.0 (not the UI origin, not the docs page)."""

    org_id: str | None = None
    """Numeric organisation id from Management -> Organisation. Never guessed
    and never defaulted to 1: a wrong org id fails every call as HTTP 400."""

    api_key: SecretStr | None = None
    """User-created API key (Management -> API Tokens). Bearer credential."""

    query_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    default_row_limit: int = Field(default=100, ge=1)
    max_row_limit: int = Field(default=1000, ge=1)

    @field_validator("org_id")
    @classmethod
    def org_id_must_be_numeric(cls, value: str | None) -> str | None:
        if value is not None and not value.isdigit():
            raise ValueError("org_id must be the numeric organisation id")
        return value

    @classmethod
    def from_env(cls) -> "ZetarisSettings":
        """Load settings, converting validation problems into a clear error."""
        try:
            settings = cls()
        except Exception as exc:  # pydantic ValidationError and friends
            raise ZetarisConfigError(f"invalid zetaris configuration: {exc}") from exc
        settings.require_credentials()
        return settings

    def require_credentials(self) -> None:
        """Fail fast with an actionable message when credentials are absent."""
        if not self.org_id:
            raise ZetarisConfigError(
                "ZETARIS_ORG_ID is not set: copy the numeric id from "
                "Management -> Organisation in the Zetaris UI"
            )
        if self.api_key is None or not self.api_key.get_secret_value():
            raise ZetarisConfigError(
                "ZETARIS_API_KEY is not set: create a key under "
                "Management -> API Tokens and store it in the local .env only"
            )

    def bearer_token(self) -> str:
        self.require_credentials()
        assert self.api_key is not None  # guaranteed by require_credentials
        return self.api_key.get_secret_value()


class ReadModelSettings(BaseSettings):
    """The product PostgreSQL as seen from inside Zetaris containers (ENG-017).

    Points at the least-privilege, SELECT-only role created for Zetaris —
    never the application superuser. On Docker Desktop, containers reach the
    host Postgres via host.docker.internal at the published port (5433). The
    password is required only when the publisher runs with --apply.
    """

    model_config = SettingsConfigDict(
        env_prefix="ZETARIS_READMODEL_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "host.docker.internal"
    port: int = Field(default=5433, gt=0, le=65535)
    database: str = "aew"
    user: str = "zetaris_ro"
    password: SecretStr | None = None
