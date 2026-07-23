"""The audit store: writes hash-chained entries (Stage 6 / Stage 8,
docs/INTERPOSE_SCOPING.md Section 6.5 and 6.7).

Every field that goes into the hash (Section 6.7's formula, implemented in
`interpose.audit.chain`) is set explicitly in Python before the row is inserted --
including `timestamp`, using the application's clock rather than Postgres's
server-side default. That's a deliberate MVP simplification: computing the hash
*before* insert needs to know every hashed field's final value in advance, but a
Postgres-server-authoritative timestamp is only known *after* insert -- and rewriting
the row afterward to fix that up isn't an option, since the audit table's writer role
only has INSERT (Section 10.7's append-only enforcement). Real timestamp signing is
already flagged in the scoping doc as v0.2 scope for regulated deployments; this MVP
accepts the application clock as authoritative instead.

Concurrent writers are serialized with a Postgres advisory lock scoped to the whole
chain: each new entry's `prev_hash` must be the immediately-prior entry's `this_hash`,
so two writers racing to read "the latest entry" without a lock could both build on
the same `prev_hash` and corrupt the chain.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.audit.chain import GENESIS_HASH, compute_entry_hash
from interpose.audit.models import AuditEntry

# Arbitrary fixed key identifying the audit-chain advisory lock. Any stable int64
# works; it has no meaning beyond distinguishing this lock from unrelated ones.
_CHAIN_LOCK_KEY = 8_784_213_001


class AuditStore:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def write_entry(
        self,
        *,
        status: str,
        trace_id: uuid.UUID,
        span_id: uuid.UUID,
        agent_id: str,
        session_id: str,
        server: str,
        tool: str,
        args_hash: str,
        args_redacted: dict[str, Any],
        policies_fired: list[dict[str, Any]],
        decision: dict[str, Any],
        parent_id: int | None = None,
        latency_ms: int | None = None,
        tokens: dict[str, Any] | None = None,
        hitl_ticket_id: uuid.UUID | None = None,
        hitl_reviewer: str | None = None,
        hitl_decision: str | None = None,
        hitl_rationale: str | None = None,
    ) -> AuditEntry:
        fields: dict[str, Any] = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_id": parent_id,
            "timestamp": datetime.now(UTC),
            "status": status,
            "agent_id": agent_id,
            "session_id": session_id,
            "server": server,
            "tool": tool,
            "args_hash": args_hash,
            "args_redacted": args_redacted,
            "policies_fired": policies_fired,
            "decision": decision,
            "latency_ms": latency_ms,
            "tokens": tokens,
            "hitl_ticket_id": hitl_ticket_id,
            "hitl_reviewer": hitl_reviewer,
            "hitl_decision": hitl_decision,
            "hitl_rationale": hitl_rationale,
        }

        async with self._session_factory() as session, session.begin():
            # Serializes with any other writer for the lifetime of this transaction;
            # released automatically on commit/rollback (`_xact_lock`).
            await session.execute(select(func.pg_advisory_xact_lock(_CHAIN_LOCK_KEY)))

            prev_hash = (
                await session.scalar(
                    select(AuditEntry.this_hash).order_by(AuditEntry.id.desc()).limit(1)
                )
                or GENESIS_HASH
            )
            fields["prev_hash"] = prev_hash
            fields["this_hash"] = compute_entry_hash(prev_hash, fields)

            entry = AuditEntry(**fields)
            session.add(entry)
            await session.flush()  # populates entry.id from the DB sequence

        return entry
