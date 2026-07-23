"""In-process pub/sub event bus (docs/INTERPOSE_SCOPING.md Section 6.9, and the
"documented seam" named in Section 6.17: `interpose.control_plane.bus.EventBus`).

An `asyncio.Queue` under the hood -- publishing is a fast, non-blocking handoff, so
the gateway's hot path is never slowed down by how long control-plane processing
takes (Section 7.12: "Control plane is async from the hot path"). Swapping this for a
Redis Stream later (for horizontal scaling, multiple gateway replicas) means changing
this one class; nothing that calls `publish`/`consume` needs to change.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from interpose.control_plane.state import DecisionEvent


class EventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DecisionEvent] = asyncio.Queue()

    async def publish(self, event: DecisionEvent) -> None:
        await self._queue.put(event)

    async def consume(self) -> AsyncIterator[DecisionEvent]:
        while True:
            yield await self._queue.get()
