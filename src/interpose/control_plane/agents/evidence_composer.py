"""Agent A3 -- Evidence Composer (docs/INTERPOSE_SCOPING.md Section 7.9).

Deterministic core: the last 20 tool calls in this session, the policy rules that
actually matched (straight off the event itself), Agent A1's risk-score components
(always present -- Section 7.6 routes `HOLD` through A1 before A3, never around it),
and prior HITL decisions for this same agent+tool combination as a simplified stand-in
for "prior HITL decisions by same reviewer group on similar patterns" -- genuine
pattern-similarity matching is out of scope; same agent, same tool, past outcome is an
honest, much simpler proxy.

`state.anomaly` is expected to be `None` here, always, in the current graph topology:
Agent A2 and Agent A3 sit on separate, non-overlapping routing paths (`HOLD` -> A1 ->
A3; `PASS` + elevated risk -> A1 -> A2). Section 7.9 lists a "related AnomalyFlag (if
any)" as optional input; today it's never populated, which is expected, not a bug.

LLM usage is this agent's primary role (Section 7.9), mandatory -- unlike Agent A2's
optional one-sentence description. A failure still produces a packet (a resilient
fallback narrative) rather than none at all: a HITL reviewer needs *something* to act
on even when generation fails.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.audit.models import AuditEntry
from interpose.control_plane.llm import LLMError, generate_structured
from interpose.control_plane.state import HITLPacket, InterposeState

RECENT_CALLS_LIMIT = 20


class SessionEvidence(BaseModel):
    recent_calls: list[dict[str, str]]
    prior_same_tool_hitl_decisions: dict[str, int]


async def compute_session_evidence(
    session_factory: async_sessionmaker, agent_id: str, session_id: str, tool: str
) -> SessionEvidence:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEntry.tool, AuditEntry.status, AuditEntry.timestamp)
                .where(AuditEntry.session_id == session_id)
                .order_by(AuditEntry.timestamp.desc())
                .limit(RECENT_CALLS_LIMIT)
            )
        ).all()
        recent_calls = [
            {"tool": r.tool, "status": r.status, "timestamp": r.timestamp.isoformat()}
            for r in rows
        ]

        prior_decisions = (
            await session.execute(
                select(AuditEntry.hitl_decision).where(
                    AuditEntry.agent_id == agent_id,
                    AuditEntry.tool == tool,
                    AuditEntry.hitl_decision.is_not(None),
                )
            )
        ).scalars().all()

    counts: dict[str, int] = {}
    for decision in prior_decisions:
        counts[decision] = counts.get(decision, 0) + 1
    return SessionEvidence(recent_calls=recent_calls, prior_same_tool_hitl_decisions=counts)


class HitlNarrativeOutput(BaseModel):
    narrative: str
    recommended_action: Literal["approve", "deny", "escalate"]
    confidence: float


async def _compose_hitl_narrative(
    state: InterposeState,
    evidence: SessionEvidence,
    generate_fn: Callable[..., Awaitable[BaseModel]],
) -> HitlNarrativeOutput:
    assert state.enriched is not None  # guaranteed by routing; see module docstring
    try:
        return await generate_fn(
            system_prompt=(
                "You are a compliance analyst composing a HITL (human-in-the-loop) "
                "review packet. Write a 3-5 sentence narrative answering: what "
                "happened, why it needs review, what the recommended action is, and "
                "what the reviewer should verify before deciding. Recommend one of: "
                "approve, deny, escalate, with a confidence between 0 and 1."
            ),
            user_prompt=(
                f"Tool: {state.event.tool}, server: {state.event.server}\n"
                f"Fired policy: {state.event.decision.fired_policy}\n"
                f"Session risk score: {state.enriched.session_risk_score:.2f}\n"
                f"Session risk features: {state.enriched.context_features}\n"
                f"Recent session calls: {evidence.recent_calls}\n"
                f"Prior HITL decisions for this agent+tool: "
                f"{evidence.prior_same_tool_hitl_decisions}"
            ),
            output_model=HitlNarrativeOutput,
        )
    except LLMError as exc:
        return HitlNarrativeOutput(
            narrative=(
                f"HITL hold on {state.event.tool} ({state.event.server}) for agent "
                f"{state.event.agent_id}, fired policy "
                f"{state.event.decision.fired_policy!r}. Narrative generation failed "
                f"({exc}); manual review required with no automated recommendation."
            ),
            recommended_action="escalate",
            confidence=0.0,
        )


NodeFn = Callable[[InterposeState], Awaitable[dict]]


def make_evidence_composer_node(
    session_factory: async_sessionmaker,
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> NodeFn:
    async def node(state: InterposeState) -> dict:
        if state.event.hitl_ticket_id is None:
            raise RuntimeError(
                "evidence_composer reached without a HITL ticket ID -- expected only "
                "on the HOLD path, which always sets one"
            )
        if state.enriched is None:
            raise RuntimeError(
                "evidence_composer reached with no enrichment from Agent A1 -- "
                "routing invariant violated (HOLD should always go through A1 first)"
            )

        evidence = await compute_session_evidence(
            session_factory, state.event.agent_id, state.event.session_id, state.event.tool
        )
        output = await _compose_hitl_narrative(state, evidence, generate_fn)
        packet = HITLPacket(
            ticket_id=state.event.hitl_ticket_id,
            event=state.event,
            enriched=state.enriched,
            narrative=output.narrative,
            recommended_action=output.recommended_action,
            confidence=output.confidence,
        )
        return {"hitl_packet": packet}

    return node
