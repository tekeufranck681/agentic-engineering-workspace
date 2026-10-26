"""Configuration for the ModelGateway (ENG-008).

Routing is configuration, not code: each capability maps to a Nightshift lane
or a pinned model id, and a capability without an entry uses the default lane.
Lanes are routing modes, so the model that actually answered is read from each
call's receipt, never inferred from the lane. The connection itself (URL and
token) stays in the NIGHTSHIFT_* settings.
"""

import re

from dotenv import find_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_LANE = "meterless/auto"
# Generous on purpose: in the live run a reasoning model spent ~190 tokens
# before a one-word answer, and structured replies are far longer.
DEFAULT_MAX_TOKENS = 4096
# "<namespace>/<name>": meterless/auto, meterless/<class>.<disposition>,
# nvidia/nemotron-3.5-lightning-30b-a3b, webllm/Llama-3.2-1B-Instruct-q4f16_1-MLC.
_MODEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9._:-]*$")

# Same .env discovery as the other settings: walk upward from the working directory.
_ENV_FILE = find_dotenv(".env", usecwd=True) or ".env"


def _check_model_id(value: str) -> str:
    value = value.strip()
    if not _MODEL_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{value!r} is not a lane or model id such as meterless/auto or nvidia/<model>")
    return value


class ModelGatewaySettings(BaseSettings):
    """Lane routing and generation defaults, from MODEL_GATEWAY_* variables."""

    model_config = SettingsConfigDict(
        env_prefix="MODEL_GATEWAY_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    default_lane: str = DEFAULT_LANE
    """Lane or model id for capabilities without their own entry."""

    lanes: dict[str, str] = Field(default_factory=dict)
    """Capability -> lane or pinned model id, as JSON in MODEL_GATEWAY_LANES,
    e.g. {"evaluation.evaluate": "nvidia/nemotron-3.5-lightning-30b-a3b"}."""

    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0, le=32768)
    """Completion budget per call, reasoning tokens included."""

    temperature: float | None = Field(default=None, ge=0, le=2)
    """Sent only when set; otherwise the runtime's routing decides."""

    @field_validator("default_lane")
    @classmethod
    def default_lane_is_a_model_id(cls, value: str) -> str:
        return _check_model_id(value)

    @field_validator("lanes")
    @classmethod
    def lanes_are_model_ids(cls, value: dict[str, str]) -> dict[str, str]:
        return {capability: _check_model_id(lane) for capability, lane in value.items()}

    def lane_for(self, capability: str | None) -> str:
        """The lane or pinned model id this capability's calls go to."""
        if capability is not None and capability in self.lanes:
            return self.lanes[capability]
        return self.default_lane
