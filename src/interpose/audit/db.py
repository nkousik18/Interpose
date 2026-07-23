"""Async SQLAlchemy engine/session setup for the audit store."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    # expire_on_commit=False: every field on a written AuditEntry is set explicitly in
    # Python before insert (see store.py) except the DB-generated `id`, which SQLAlchemy
    # populates on the object immediately after flush regardless of this setting. So the
    # in-memory object stays a valid, fully-populated source of truth after commit,
    # without needing an async-aware lazy-refresh from the database.
    return async_sessionmaker(engine, expire_on_commit=False)
