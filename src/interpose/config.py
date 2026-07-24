"""Process-wide settings, loaded from environment variables (and `.env` in dev).

Settings get added here when the feature that needs them actually lands (see
`.env.example`) -- e.g. `redis_url` arrived with Day 6's HITL ticket queue, not before.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://interpose:interpose_dev@localhost:5433/interpose"
    redis_url: str = "redis://localhost:6379/0"
    # Anthropic Claude is the eventual default per Section 6.4; Groq is configured for
    # now because it has a genuinely free tier, and the scoping doc names it as an
    # anticipated alternative provider. See concepts/24-narrative-generation-with-a-real-llm.md.
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    # Bind address/port for `python -m interpose.gateway`. 127.0.0.1 stays the default
    # for bare-metal local dev (docker-compose Postgres/Redis, no container around the
    # gateway itself); the Helm chart's Deployment overrides GATEWAY_HOST=0.0.0.0 via
    # env, since inside a Pod the gateway must accept traffic from the Service, not
    # just localhost. See concepts/26-helm-and-the-interpose-chart.md.
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8000
    # Same local-file-vs-mounted-ConfigMap duality as the rest of config/ -- unchanged
    # default for local dev; the chart overrides these to the paths it mounts
    # config/upstreams.yaml and config/policies/ at inside the container.
    config_path: str = "config/upstreams.yaml"
    policy_dir: str = "config/policies"


@lru_cache
def get_settings() -> Settings:
    return Settings()
