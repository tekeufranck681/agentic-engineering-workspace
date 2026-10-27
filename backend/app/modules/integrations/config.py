"""Configuration for the ENG-042 sponsor health checks (SPONSOR_HEALTH_*).

Only the optional Nightshift chat ping is configurable here: the discovery
probe is fixed by the provider guide, while the lane used for the bounded
chat completion must be pinnable to any model id the runtime actually serves
(a routing lane such as ``meterless/auto`` can point at a function that is
not provisioned for the current account).
"""

import re

from dotenv import find_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CHAT_LANE = "meterless/auto"
# Match the proven ENG-003 Nightshift smoke: reasoning Nemotron models spend
# hundreds of tokens before the visible answer, and a small cap makes the
# Meterless runtime route to a function path that can fail (observed 502
# "Function ... Not found" with max_tokens=16 on a reasoning lane).
DEFAULT_CHAT_MAX_TOKENS = 1024
# Same shape rule as ModelGatewaySettings: "<namespace>/<name>".
_MODEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9._:-]*$")

# Resolve .env by walking upward from the working directory, like every other
# settings module, so runs from repo root or backend/ read the same file.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


class IntegrationSettings(BaseSettings):
    """Settings for sponsor integration health checks."""

    model_config = SettingsConfigDict(
        env_prefix="SPONSOR_HEALTH_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    chat_lane: str = DEFAULT_CHAT_LANE
    """Lane or pinned model id for the optional --chat Nightshift ping."""

    chat_max_tokens: int = Field(default=DEFAULT_CHAT_MAX_TOKENS, gt=0, le=4096)
    """Bounded but generous: the ping proves a model response, and reasoning
    models need headroom before their visible answer."""

    @field_validator("chat_lane")
    @classmethod
    def chat_lane_is_a_model_id(cls, value: str) -> str:
        value = value.strip()
        if not _MODEL_ID_PATTERN.fullmatch(value):
            raise ValueError(
                f"{value!r} is not a lane or model id such as meterless/auto or nvidia/<model>"
            )
        return value
