"""Configuration for GitHub access (M5).

The agent may only ever modify the demo-target repository. The product
repository is configured too, but only so the preflight can prove the token
cannot write it. The token is a SecretStr and lives in the local .env only.
"""

import re

from dotenv import find_dotenv
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_URL = "https://api.github.com"
DEFAULT_PRODUCT_REPO = "tekeufranck681/agentic-engineering-workspace"

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class GitHubConfigError(Exception):
    """Settings are missing or unsafe; nothing was sent to GitHub."""


class GitHubSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GITHUB_", env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    api_url: str = DEFAULT_API_URL
    token: SecretStr | None = None
    """Fine-grained personal access token restricted to the demo-target repo."""

    demo_repo: str = ""
    """``owner/name`` of the throwaway repository the agent is allowed to change."""

    product_repo: str = DEFAULT_PRODUCT_REPO
    """``owner/name`` of this product's repository; the token must NOT write it."""

    timeout_seconds: float = Field(default=15.0, gt=0, le=120)

    agent_branch_prefix: str = "aew/"
    """The agent may only create, push to, open PRs from and delete branches
    under this prefix. The default branch is never written."""

    max_file_bytes: int = Field(default=200_000, ge=1_000, le=5_000_000)
    """Largest file the adapter will read or write."""

    @field_validator("api_url")
    @classmethod
    def strip_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("agent_branch_prefix")
    @classmethod
    def prefix_is_a_namespace(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*/", value):
            raise ValueError("agent_branch_prefix must look like 'aew/'")
        return value

    @field_validator("demo_repo", "product_repo")
    @classmethod
    def repo_format(cls, value: str) -> str:
        value = value.strip()
        if value and not _REPO_PATTERN.fullmatch(value):
            raise ValueError(f"expected owner/name, got {value!r}")
        return value

    @model_validator(mode="after")
    def demo_is_not_product(self) -> "GitHubSettings":
        if self.demo_repo and self.demo_repo.lower() == self.product_repo.lower():
            raise ValueError("GITHUB_DEMO_REPO must be a separate throwaway repo, not the product repo")
        return self

    @classmethod
    def from_env(cls) -> "GitHubSettings":
        try:
            settings = cls()
        except Exception as exc:
            raise GitHubConfigError(f"invalid GitHub configuration: {exc}") from exc
        if not settings.demo_repo:
            raise GitHubConfigError("GITHUB_DEMO_REPO is not set (owner/name of the throwaway demo repo)")
        if not settings.token or not settings.token.get_secret_value().strip():
            raise GitHubConfigError(
                "GITHUB_TOKEN is not set: create a fine-grained token limited to the demo repo "
                "and put it in the local .env only"
            )
        return settings

    def bearer_token(self) -> str:
        assert self.token is not None
        return self.token.get_secret_value().strip()
