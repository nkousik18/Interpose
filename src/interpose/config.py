"""Process-wide settings, loaded from environment variables (and `.env` in dev).

Only `database_url` exists so far because it's the only thing that currently needs
to be configurable across environments. More settings (LLM provider/API key, Redis
URL, ...) get added here when the feature that needs them actually lands -- see
`.env.example`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://interpose:interpose_dev@localhost:5433/interpose"


@lru_cache
def get_settings() -> Settings:
    return Settings()
