"""Configuration for the Nightshift client.

Values come from the environment (or the local .env file) and never from
prompts or code. The runtime token is wrapped in SecretStr so it cannot leak
through reprs or logs, and validation errors never echo input values. The app
shows the token under Console > API key; the Mac M1-M4 app also keeps it in
its state directory as ``runtime-token`` (the provider guide calls the file
``proxy-token``). Copy it into the local .env only.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from dotenv import find_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.modules.nightshift.errors import NightshiftConfigError

DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_APP_ID = "agentic-engineering-workspace"
PLACEHOLDER_TOKEN = "rt-local"

# Paths a pasted URL may end with: the provider guide's forms plus the hotspot
# connect link. Longest first so "/v1/models" is stripped whole instead of
# leaving "/v1" behind.
_PASTED_SUFFIXES = ("/v1/chat/completions", "/v1/models", "/healthz", "/connect", "/v1")
_APP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# Resolve .env by walking upward from the working directory, so the module
# finds the root .env whether it runs from the repo root or from backend/.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


def normalize_base_url(raw: str) -> str:
    """Normalize a pasted runtime URL to ``<scheme>://<host>[:port]/v1``.

    Accepts the forms the provider guide lists: with or without a scheme,
    ending in /v1, /v1/chat/completions, /v1/models or /healthz, and the
    hotspot connect link ``http://<host>:8088/connect#k=<token>``. Query and
    fragment are always dropped: the connect link carries the token there, and
    the token belongs in NIGHTSHIFT_TOKEN, never in a URL that gets printed
    and recorded as evidence. Never produces /v1/v1.
    """
    url = raw.strip()
    if not url:
        raise ValueError("base URL is empty")
    if "://" not in url:
        url = f"http://{url}"
    parts = urlsplit(url)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).rstrip("/")
    for suffix in _PASTED_SUFFIXES:
        if url.endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
            break
    return f"{url}/v1"


class NightshiftSettings(BaseSettings):
    """Connection settings for the Meterless Runtime served by Nightshift."""

    model_config = SettingsConfigDict(
        env_prefix="NIGHTSHIFT_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,  # a misplaced secret is never echoed in a CONFIG error
    )

    base_url: str = DEFAULT_BASE_URL
    """OpenAI-compatible base URL. On the backend host this is the Nightshift
    machine's LAN address (hotspot mode), not localhost."""

    token: SecretStr | None = None
    """Runtime API key (Nightshift Console > API key, or ``runtime-token`` in the
    Mac app's state directory). Bearer credential."""

    app_id: str = DEFAULT_APP_ID
    """Stable lowercase id sent as ``meterless-app`` on every request."""

    timeout_seconds: float = Field(default=180.0, gt=0, le=900)
    """Read timeout for chat calls; a cold model load can take minutes."""

    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @field_validator("base_url")
    @classmethod
    def base_url_must_normalize(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("app_id")
    @classmethod
    def app_id_must_be_stable_lowercase(cls, value: str) -> str:
        if not _APP_ID_PATTERN.fullmatch(value):
            raise ValueError("app_id must be a stable lowercase id (a-z, 0-9, '.', '_', '-')")
        return value

    @classmethod
    def from_env(cls) -> "NightshiftSettings":
        """Load settings, converting validation problems into a clear error."""
        try:
            settings = cls()
        except Exception as exc:  # pydantic ValidationError and friends
            raise NightshiftConfigError(f"invalid nightshift configuration: {exc}") from exc
        settings.require_credentials()
        return settings

    def require_credentials(self) -> None:
        """Fail fast with an actionable message when the token is unusable."""
        token = self.token.get_secret_value().strip() if self.token else ""
        if not token:
            raise NightshiftConfigError(
                "NIGHTSHIFT_TOKEN is not set: copy the runtime API key "
                "(Nightshift Console > API key) into the local .env only"
            )
        if token == PLACEHOLDER_TOKEN:
            raise NightshiftConfigError(
                f"NIGHTSHIFT_TOKEN is the placeholder {PLACEHOLDER_TOKEN!r}, which the "
                "runtime rejects; use the real API key from Nightshift Console > API key"
            )

    def bearer_token(self) -> str:
        self.require_credentials()
        assert self.token is not None  # guaranteed by require_credentials
        return self.token.get_secret_value().strip()
