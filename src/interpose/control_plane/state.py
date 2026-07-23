"""The control-plane's typed state model (docs/INTERPOSE_SCOPING.md Section 7.4).

Everything here is a Pydantic model, not free text -- per design principle P2 (Section
7.2): the LangGraph state is a structured object, agents are Pydantic-in/Pydantic-out
functions, not a chat transcript. `InterposeState` is what flows through the graph
(`interpose.control_plane.graph`); every node reads and writes typed slots on it.

Only `event` and `enriched` are populated by anything real as of Phase 2 Day 6 --
Agents A2/A3/A4 (which would populate `anomaly`/`hitl_packet`/`incident`) are
placeholder stub nodes until Day 8. The full state shape is defined now regardless,
matching the doc's schema exactly, since it's one typed contract, not five separate
ones to bolt on incrementally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class PolicyResult(BaseModel):
    policy: str
    effect_type: str


class Decision(BaseModel):
    outcome: str
    fired_policy: str | None = None
    reason: str | None = None


class DecisionEvent(BaseModel):
    audit_id: int
    trace_id: UUID
    agent_id: str
    session_id: str
    server: str
    tool: str
    args_hash: str
    policies_fired: list[PolicyResult]
    decision: Decision
    timestamp: datetime


class EnrichedDecision(BaseModel):
    event: DecisionEvent
    context_features: dict[str, float]
    session_risk_score: float
    session_call_history_summary: str | None = None


class AnomalyFlag(BaseModel):
    event: DecisionEvent
    anomaly_type: str
    severity: Literal["low", "med", "high"]
    evidence: dict[str, Any]


class HITLPacket(BaseModel):
    ticket_id: UUID
    event: DecisionEvent
    enriched: EnrichedDecision
    narrative: str
    recommended_action: Literal["approve", "deny", "escalate"]
    confidence: float


class Incident(BaseModel):
    incident_id: UUID
    related_events: list[int]
    severity: Literal["low", "med", "high"]
    narrative: str
    recommended_response: str
    created_at: datetime


class InterposeState(BaseModel):
    event: DecisionEvent
    enriched: EnrichedDecision | None = None
    anomaly: AnomalyFlag | None = None
    hitl_packet: HITLPacket | None = None
    incident: Incident | None = None
    error: str | None = None
