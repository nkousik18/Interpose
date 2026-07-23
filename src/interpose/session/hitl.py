"""The HITL ticket queue (docs/INTERPOSE_SCOPING.md Section 6.8, Phase 2 Day 6).

Redis key layout:
- `interpose:hitl:{ticket_id}` -- a hash, the ticket itself. TTL is the policy's
  `timeout_seconds` plus a grace period, so a ticket decided right at the buzzer is
  still readable by the gateway's next poll before it's naturally reclaimed.
- `interpose:hitl:pending` -- a set of ticket_ids currently PENDING, so `interpose
  review list` doesn't need a full keyspace scan to find them.

Async operations (`create_ticket`, `get_ticket`, `wait_for_decision`) are used by the
gateway, which is async throughout. Sync operations (`list_pending`, `decide_ticket`)
are used by the `interpose review` CLI, a one-shot synchronous command -- same split
as `interpose.audit`'s async engine (gateway) vs. sync engine (CLI/Alembic).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import redis
import redis.asyncio as aioredis

PENDING_SET_KEY = "interpose:hitl:pending"
# Keeps a just-decided ticket readable a bit past its nominal timeout, rather than
# racing the gateway's final poll against Redis's own expiry.
TICKET_TTL_GRACE_SECONDS = 300

Status = Literal["PENDING", "APPROVED", "DENIED"]


def _ticket_key(ticket_id: str) -> str:
    return f"interpose:hitl:{ticket_id}"


@dataclass
class HitlTicket:
    ticket_id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    agent_id: str
    session_id: str
    trace_id: str
    audit_entry_id: int
    reviewer_group: str
    timeout_seconds: int
    status: Status
    created_at: float
    decided_by: str | None = None
    decided_at: float | None = None
    rationale: str | None = None

    def to_redis(self) -> dict[str, str]:
        return {
            "ticket_id": self.ticket_id,
            "server": self.server,
            "tool": self.tool,
            "arguments": json.dumps(self.arguments),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "audit_entry_id": str(self.audit_entry_id),
            "reviewer_group": self.reviewer_group,
            "timeout_seconds": str(self.timeout_seconds),
            "status": self.status,
            "created_at": str(self.created_at),
            "decided_by": self.decided_by or "",
            "decided_at": str(self.decided_at) if self.decided_at is not None else "",
            "rationale": self.rationale or "",
        }

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> HitlTicket:
        return cls(
            ticket_id=data["ticket_id"],
            server=data["server"],
            tool=data["tool"],
            arguments=json.loads(data["arguments"]),
            agent_id=data["agent_id"],
            session_id=data["session_id"],
            trace_id=data["trace_id"],
            audit_entry_id=int(data["audit_entry_id"]),
            reviewer_group=data["reviewer_group"],
            timeout_seconds=int(data["timeout_seconds"]),
            status=data["status"],  # type: ignore[arg-type]
            created_at=float(data["created_at"]),
            decided_by=data["decided_by"] or None,
            decided_at=float(data["decided_at"]) if data["decided_at"] else None,
            rationale=data["rationale"] or None,
        )


async def create_ticket(
    conn: aioredis.Redis,
    *,
    server: str,
    tool: str,
    arguments: dict[str, Any],
    agent_id: str,
    session_id: str,
    trace_id: str,
    audit_entry_id: int,
    reviewer_group: str,
    timeout_seconds: int,
) -> HitlTicket:
    ticket = HitlTicket(
        ticket_id=str(uuid.uuid4()),
        server=server,
        tool=tool,
        arguments=arguments,
        agent_id=agent_id,
        session_id=session_id,
        trace_id=trace_id,
        audit_entry_id=audit_entry_id,
        reviewer_group=reviewer_group,
        timeout_seconds=timeout_seconds,
        status="PENDING",
        created_at=time.time(),
    )
    key = _ticket_key(ticket.ticket_id)
    async with conn.pipeline(transaction=True) as pipe:
        pipe.hset(key, mapping=ticket.to_redis())
        pipe.expire(key, timeout_seconds + TICKET_TTL_GRACE_SECONDS)
        pipe.sadd(PENDING_SET_KEY, ticket.ticket_id)
        await pipe.execute()
    return ticket


async def get_ticket(conn: aioredis.Redis, ticket_id: str) -> HitlTicket | None:
    data = await conn.hgetall(_ticket_key(ticket_id))
    if not data:
        return None
    return HitlTicket.from_redis(data)


async def wait_for_decision(
    conn: aioredis.Redis,
    ticket_id: str,
    timeout_seconds: int,
    poll_interval: float = 0.25,
) -> HitlTicket | None:
    """Poll until the ticket leaves PENDING or `timeout_seconds` elapses.

    Returns the last-seen ticket either way -- if it's still PENDING on return, the
    caller should treat that as a timeout. Returns None only if the ticket vanished
    entirely (e.g. Redis eviction), which the caller should also treat as a timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        ticket = await get_ticket(conn, ticket_id)
        if ticket is None or ticket.status != "PENDING":
            return ticket
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ticket
        await asyncio.sleep(min(poll_interval, remaining))


def list_pending(conn: redis.Redis) -> list[HitlTicket]:
    tickets = []
    for ticket_id in conn.smembers(PENDING_SET_KEY):
        data = conn.hgetall(_ticket_key(ticket_id))
        if not data:
            conn.srem(PENDING_SET_KEY, ticket_id)  # expired -- drop the stale index entry
            continue
        tickets.append(HitlTicket.from_redis(data))
    return tickets


def decide_ticket(
    conn: redis.Redis,
    ticket_id: str,
    *,
    status: Literal["APPROVED", "DENIED"],
    decided_by: str,
    rationale: str,
) -> tuple[HitlTicket, bool] | None:
    """Returns None if the ticket doesn't exist. Otherwise (ticket, applied): `applied`
    is False if the ticket had already been decided (by anyone) before this call --
    idempotent, doesn't overwrite the record of who actually decided it first, but the
    caller (the CLI) can still tell "you just decided this" apart from "no-op, already
    settled" and report accordingly."""
    key = _ticket_key(ticket_id)
    data = conn.hgetall(key)
    if not data:
        return None
    ticket = HitlTicket.from_redis(data)
    if ticket.status != "PENDING":
        return ticket, False
    ticket.status = status
    ticket.decided_by = decided_by
    ticket.decided_at = time.time()
    ticket.rationale = rationale
    conn.hset(key, mapping=ticket.to_redis())
    conn.srem(PENDING_SET_KEY, ticket_id)
    return ticket, True
