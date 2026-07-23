"""Unit tests for the in-process EventBus (interpose.control_plane.bus)."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from interpose.control_plane.bus import EventBus
from interpose.control_plane.state import Decision, DecisionEvent


def _event(audit_id: int) -> DecisionEvent:
    return DecisionEvent(
        audit_id=audit_id,
        trace_id=uuid4(),
        agent_id="agent-1",
        session_id="sess-1",
        server="hello-echo",
        tool="echo",
        args_hash="deadbeef",
        policies_fired=[],
        decision=Decision(outcome="PASS"),
        timestamp=datetime.now(UTC),
    )


async def test_publish_then_consume_returns_the_same_event() -> None:
    bus = EventBus()
    event = _event(1)
    await bus.publish(event)

    consumer = bus.consume()
    received = await anext(consumer)
    assert received == event


async def test_consume_yields_events_in_publish_order() -> None:
    bus = EventBus()
    for i in range(5):
        await bus.publish(_event(i))

    consumer = bus.consume()
    received = [await anext(consumer) for _ in range(5)]
    assert [e.audit_id for e in received] == [0, 1, 2, 3, 4]


async def test_consume_blocks_until_something_is_published() -> None:
    bus = EventBus()
    consumer = bus.consume()

    async def publish_shortly() -> None:
        await asyncio.sleep(0.05)
        await bus.publish(_event(42))

    _, received = await asyncio.gather(publish_shortly(), anext(consumer))
    assert received.audit_id == 42
