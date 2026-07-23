"""Agent A1 -- Policy Evaluator (docs/INTERPOSE_SCOPING.md Section 7.7).

Enriches a DecisionEvent with session context the static policy engine can't see, by
querying the audit log directly (not the "materialized view refreshed every 15
minutes" the doc describes -- that's a Spark aggregation job that doesn't exist yet;
a live query is simpler and entirely sufficient at today's data volume).

No LLM call happens here. Section 7.7 gates the narrative-generation LLM call on "a
HITL packet ... going to be composed downstream" -- that's Agent A3, which doesn't
exist until Day 8, so this agent has zero LLM usage for now, matching design
principle P1 (deterministic where possible).

Three of Section 7.7's feature list are deliberately not computed -- each missing a
concrete, named dependency, not just "not gotten to yet":
- read/write ratio: needs a registry classifying each tool as read or write action.
  No such registry exists (policies match by name, not by declared action type).
- sanctions-check frequency: an AML-specific signal; the OFAC sanctions MCP server
  doesn't exist before Phase 3.
- per-tool baseline z-scores: needs a historical baseline store, which is the same
  missing materialized view/Spark job mentioned above.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.audit.models import AuditEntry
from interpose.control_plane.state import DecisionEvent, EnrichedDecision, InterposeState


async def compute_context_features(
    session_factory: async_sessionmaker, event: DecisionEvent
) -> dict[str, float]:
    """Deterministic features computable today from the audit log alone."""
    window_start = event.timestamp - timedelta(minutes=1)
    async with session_factory() as session:
        calls_last_minute = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.session_id == event.session_id, AuditEntry.timestamp >= window_start)
        )
        unique_tools = await session.scalar(
            select(func.count(func.distinct(AuditEntry.tool))).where(
                AuditEntry.session_id == event.session_id
            )
        )
        total_calls = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.session_id == event.session_id)
        )
        hitl_ticket_count = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.session_id == event.session_id, AuditEntry.status == "HELD")
        )
        denial_count = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.session_id == event.session_id, AuditEntry.status == "DENIED")
        )

    return {
        "calls_per_minute": float(calls_last_minute or 0),
        "unique_tools_count": float(unique_tools or 0),
        "total_calls": float(total_calls or 0),
        "hitl_ticket_count": float(hitl_ticket_count or 0),
        "denial_count": float(denial_count or 0),
    }


def compute_session_risk_score(features: dict[str, float]) -> float:
    """A simple, transparent, hand-picked-weights heuristic -- explicitly NOT a
    calibrated model. There's no production data yet to calibrate against; this
    exists so the Supervisor's second routing hop has *something* real to act on,
    not a stand-in for the kind of statistical/ML approach Section 7.8's Anomaly
    Detector (A2) will eventually use for its own, separate purpose."""
    score = (
        0.05 * features["calls_per_minute"]
        + 0.3 * min(features["denial_count"], 3)
        + 0.2 * min(features["hitl_ticket_count"], 3)
    )
    return max(0.0, min(1.0, score))


async def _record_session_risk_score(
    redis_conn: Redis, event: DecisionEvent, risk_score: float
) -> None:
    """Writes into `interpose:session:{agent_id}`-shaped state (Section 6.8) --
    scoped by session_id here since that's what a HITL/audit trail actually keys on.
    The only real reader/writer of this hash so far; the rest of Section 6.8's
    session-state fields (active HITL ticket list, ...) still aren't built."""
    await redis_conn.hset(
        f"interpose:session:{event.session_id}",
        mapping={
            "agent_id": event.agent_id,
            "risk_score": str(risk_score),
            "last_updated": str(time.time()),
        },
    )


NodeFn = Callable[[InterposeState], Awaitable[dict]]


def make_policy_evaluator_node(session_factory: async_sessionmaker, redis_conn: Redis) -> NodeFn:
    """LangGraph calls a node as `node(state)` -- dependencies (the DB session
    factory, the Redis connection) are bound via this closure at graph-build time
    rather than threaded through LangGraph's own call signature."""

    async def node(state: InterposeState) -> dict:
        features = await compute_context_features(session_factory, state.event)
        risk_score = compute_session_risk_score(features)
        await _record_session_risk_score(redis_conn, state.event, risk_score)
        enriched = EnrichedDecision(
            event=state.event,
            context_features=features,
            session_risk_score=risk_score,
            session_call_history_summary=None,  # LLM narrative deferred to Agent A3
        )
        return {"enriched": enriched}

    return node
