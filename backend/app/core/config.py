"""Application settings (ENG-009, owned by M4).

Config is read from the environment (or a local .env file); nothing secret
lives in code. Discovered by walking upward from the working directory so
running from either the repo root or backend/ finds the same file.
"""

from functools import lru_cache

from dotenv import find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env by walking upward from the working directory, so running from
# either the repo root or backend/ finds the same file. Falls back to the
# plain relative name when nothing is found (silently ignored then).
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class Settings(BaseSettings):
    """Runtime settings resolved from the environment."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./aew-dev.db"
    """SQLAlchemy URL. PostgreSQL in team/dev environments, SQLite allowed for
    zero-setup local runs and tests."""

    log_level: str = "INFO"
    """Root log level: DEBUG, INFO, WARNING, ERROR, or CRITICAL."""


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the .env file is read once per process."""
    return Settings()
