"""Settings for the evidence object store (ENG-037).

Follows the module-local settings pattern of app/modules/zetaris/config.py:
values come from the environment (or local .env), never from code constants
that pretend to be configuration.
"""

from pathlib import Path

from dotenv import find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env by walking upward from the working directory (DISC-M2-05
# pattern), so the module behaves the same from repo root or backend/.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"

# backend/app/modules/persistence/evidence_config.py -> persistence, modules,
# app, backend, repo root. Anchoring the default to __file__ keeps the store
# location independent of the caller's working directory.
_DEFAULT_ROOT = Path(__file__).resolve().parents[4] / "var" / "evidence"


class EvidenceSettings(BaseSettings):
    """Object-store settings."""

    model_config = SettingsConfigDict(
        env_prefix="AEW_EVIDENCE_", env_file=_ENV_FILE, env_file_encoding="utf-8",
        extra="ignore",
    )

    root: Path = _DEFAULT_ROOT
    """Object-store root; default <repo>/var/evidence (git-ignored). Override
    with AEW_EVIDENCE_ROOT to keep the store outside the checkout."""
