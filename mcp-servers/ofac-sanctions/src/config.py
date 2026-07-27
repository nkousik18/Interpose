"""Settings for the OFAC sanctions MCP server -- deliberately its own tiny
Settings, not interpose.config.Settings: this is meant to be a genuinely separate
service, with its own environment, not a module inside the gateway.
"""

from __future__ import annotations

from loader import ALT_URL, DEFAULT_MATCH_THRESHOLD, SDN_URL
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OFAC_", env_file=".env", extra="ignore")

    # Either a URL (fetched live) or a local file path (read from disk) -- a path is
    # what tests and offline local dev use instead of the live Treasury URL, same
    # "override for dev/test, real thing by default" shape as the rest of this
    # project's Settings classes.
    sdn_source: str = SDN_URL
    alt_source: str = ALT_URL
    match_threshold: float = DEFAULT_MATCH_THRESHOLD
    host: str = "127.0.0.1"
    port: int = 9002
