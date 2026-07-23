"""Agent A4 -- Incident Escalator (docs/INTERPOSE_SCOPING.md Section 7.10).

Of Section 7.10's four promotion rules:
- "Single DENY on a sanctions-check tool" -- not implemented; that tool doesn't
  exist before Phase 3.
- "3+ DENYs from same agent within 15 minutes" -- real. Computed independently here
  (not read off `state.enriched`), because this node can be reached via the direct
  `DENY` path, which skips Agent A1 entirely (Section 7.6) -- `state.enriched` may
  simply not exist by the time this runs.
- "AnomalyFlag severity == high" -- real, when reached via Agent A2.
- "Session risk score > 0.8 with pending HITL" -- the promotion *logic* handles this
  case (so `should_promote` is fully correct regardless), but it is **not yet
  reachable via the graph**: that would require Agent A3 to conditionally continue on
  to A4 rather than always ending the graph, which isn't wired up
  (concepts/25-remaining-control-plane-agents.md explains why this is a named,
  deliberate gap rather than an oversight).

LLM usage is mandatory when an incident is promoted (Section 7.10: "When promoted,
LLM writes a ... incident narrative ... and generates a suggested response
classification"). Unlike Agent A2's optional description, a promoted incident always
needs *something* usable -- if the LLM call fails, a clear deterministic fallback
narrative is used instead of leaving the incident without one.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.audit.models import AuditEntry
from interpose.control_plane.llm import LLMError, generate_structured
from interpose.control_plane.state import Incident, InterposeState

REPEATED_DENIALS_THRESHOLD = 3
HIGH_RISK_THRESHOLD = 0.8


class IncidentSignals(BaseModel):
    denials_last_15_min: int


async def compute_incident_signals(
    session_factory: async_sessionmaker, agent_id: str, as_of: datetime
) -> IncidentSignals:
    async with session_factory() as session:
        denials = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(
                AuditEntry.agent_id == agent_id,
                AuditEntry.status == "DENIED",
                AuditEntry.timestamp >= as_of - timedelta(minutes=15),
            )
        )
    return IncidentSignals(denials_last_15_min=denials or 0)


def should_promote(state: InterposeState, signals: IncidentSignals) -> str | None:
    """Returns the name of the rule that matched, or None if no rule promotes this
    event to an incident."""
    if signals.denials_last_15_min >= REPEATED_DENIALS_THRESHOLD:
        return "repeated_denials"
    if state.anomaly is not None and state.anomaly.severity == "high":
        return "high_severity_anomaly"
    if (
        state.enriched is not None
        and state.event.decision.outcome == "HOLD"
        and state.enriched.session_risk_score > HIGH_RISK_THRESHOLD
    ):
        return "high_risk_pending_hitl"
    return None


def compute_incident_severity(rule: str, state: InterposeState) -> Literal["med", "high"]:
    """"high" if the matched rule is inherently severe, OR if a high-severity anomaly
    is present regardless of *which* rule technically matched first --
    `should_promote` checks repeated_denials before anomaly severity, so a case that
    trips both shouldn't be under-reported just because denials matched first."""
    if rule in ("high_severity_anomaly", "high_risk_pending_hitl"):
        return "high"
    if state.anomaly is not None and state.anomaly.severity == "high":
        return "high"
    return "med"


class IncidentNarrativeOutput(BaseModel):
    narrative: str
    recommended_response: Literal["monitor", "investigate", "contain", "escalate-to-security"]


async def _compose_incident_narrative(
    state: InterposeState,
    rule: str,
    generate_fn: Callable[..., Awaitable[BaseModel]],
) -> IncidentNarrativeOutput:
    try:
        return await generate_fn(
            system_prompt=(
                "You are a compliance analyst writing a 5-8 sentence incident "
                "narrative for downstream review, and classifying the recommended "
                "response as one of: monitor, investigate, contain, "
                "escalate-to-security."
            ),
            user_prompt=(
                f"Promotion rule: {rule}\nTool: {state.event.tool}, server: "
                f"{state.event.server}\nDecision: {state.event.decision.outcome} "
                f"({state.event.decision.reason})\nAgent: {state.event.agent_id}"
            ),
            output_model=IncidentNarrativeOutput,
        )
    except LLMError as exc:
        return IncidentNarrativeOutput(
            narrative=(
                f"Incident promoted under rule {rule!r} for agent "
                f"{state.event.agent_id} on {state.event.server}/{state.event.tool}. "
                f"Narrative generation failed ({exc}); manual review required."
            ),
            recommended_response="investigate",
        )


NodeFn = Callable[[InterposeState], Awaitable[dict]]


def make_incident_escalator_node(
    session_factory: async_sessionmaker,
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> NodeFn:
    async def node(state: InterposeState) -> dict:
        signals = await compute_incident_signals(
            session_factory, state.event.agent_id, state.event.timestamp
        )
        rule = should_promote(state, signals)
        if rule is None:
            return {}

        output = await _compose_incident_narrative(state, rule, generate_fn)
        incident = Incident(
            incident_id=uuid.uuid4(),
            related_events=[state.event.audit_id],
            severity=compute_incident_severity(rule, state),
            narrative=output.narrative,
            recommended_response=output.recommended_response,
            created_at=datetime.now(UTC),
        )
        return {"incident": incident}

    return node
