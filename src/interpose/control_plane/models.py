"""SQLAlchemy models for control-plane agent output that was previously computed and
discarded (Phase 3 gap-closing work, docs/project/SESSION_LOG.md): Agent A2's anomaly
flags, Agent A4's incident promotions, and Agent A1's session risk-score history.
Shares `interpose.audit.models.Base`, same reasoning as `interpose.analytics.models`
-- one migration history.

No `source` column here, unlike `interpose.analytics.models`' aggregate tables: those
distinguish real gateway traffic from Day 15's fabricated 10M-row synthetic corpus.
There is no synthetic generator for control-plane agent output -- every row in these
three tables comes from `interpose.control_plane.runner.run_forever` processing a
real `DecisionEvent`, so there's nothing to distinguish it from.

No foreign key from these tables back to `audit_entries.id`, matching
`AuditEntrySynthetic.parent_id`'s precedent (see that model's docstring): a
`DecisionEvent.audit_id` is trusted as already-real (the gateway wrote that audit row
before publishing the event onto the bus), but enforcing that with a DB-level FK would
mean every control-plane unit/integration test needs a real, seeded `audit_entries`
row with that exact id, not just a plausible one -- and several of this project's own
existing control-plane tests use a fixed placeholder `audit_id` that was never seeded.

Also deliberately *not* pre-aggregated into `agg_*` tables the way gateway telemetry
is: `interpose.analytics.aggregate_telemetry` exists because the 10M-row synthetic
corpus is too large for a dashboard panel to query directly at interactive speed.
Real control-plane traffic runs at real-gateway scale (tens to low thousands of rows
in this project's own dev/demo use, not millions) -- a plain `GROUP BY`/`WHERE
created_at > now() - interval` query against these tables directly, from the Grafana
panel itself, is simpler and just as fast. Building a Spark aggregation step for data
this size would be unnecessary machinery, not more "production-grade."
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Float, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from interpose.audit.models import Base


class AnomalyFlagRecord(Base):
    """Agent A2's output (`interpose.control_plane.agents.anomaly_detector`),
    previously held only in per-invocation LangGraph state (`InterposeState.anomaly`)
    and discarded once the graph run finished."""

    __tablename__ = "anomaly_flags"
    __table_args__ = (Index("idx_anomaly_flags_agent_time", "agent_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)


class IncidentRecord(Base):
    """Agent A4's output (`interpose.control_plane.agents.incident_escalator`),
    previously held only in per-invocation LangGraph state (`InterposeState.incident`)
    and discarded once the graph run finished. `id` reuses the `Incident.incident_id`
    already generated in the node, rather than a separate surrogate key."""

    __tablename__ = "incidents"
    __table_args__ = (Index("idx_incidents_agent_time", "agent_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Which of should_promote's rules matched (Section 7.10) -- not on the Incident
    # Pydantic model itself, but genuinely useful for the dashboard/debugging, so
    # captured here at the point the node already knows it.
    promotion_rule: Mapped[str] = mapped_column(Text, nullable=False)
    related_events: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_response: Mapped[str] = mapped_column(Text, nullable=False)


class RiskScoreSnapshot(Base):
    """Agent A1's session risk score (`interpose.control_plane.agents.policy_evaluator`),
    written alongside -- not instead of -- the live Redis hash
    (`interpose:session:{session_id}`): Redis stays the cheap "current value" read for
    other agents; this table is the durable history nothing could previously query."""

    __tablename__ = "risk_score_snapshots"
    __table_args__ = (Index("idx_risk_score_snapshots_agent_time", "agent_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audit_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    context_features: Mapped[dict] = mapped_column(JSONB, nullable=False)
