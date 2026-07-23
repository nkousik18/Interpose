"""Redis connection setup (docs/INTERPOSE_SCOPING.md Section 6.8).

Two factories, same reason `interpose.audit` has both an async engine (the gateway)
and a sync one (Alembic/the CLI): the gateway is async throughout, the `interpose
review` CLI is a synchronous one-shot command. Both talk to the same Redis server.
"""

from __future__ import annotations

import redis as sync_redis
import redis.asyncio as async_redis


def create_async_redis(redis_url: str) -> async_redis.Redis:
    return async_redis.from_url(redis_url, decode_responses=True)


def create_sync_redis(redis_url: str) -> sync_redis.Redis:
    return sync_redis.from_url(redis_url, decode_responses=True)
