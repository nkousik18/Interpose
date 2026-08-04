"""SQLAlchemy models for the analytics plane (docs/INTERPOSE_SCOPING.md Section
10.6, 12.4; Phase 3 Day 15): synthetic gateway telemetry for the Spark demo, and the
aggregate tables `interpose.analytics.aggregate_telemetry` produces for Grafana's
Postgres-backed dashboards.

Shares `interpose.audit.models.Base` (and therefore Alembic's `target_metadata`)
rather than defining a second declarative base -- one migration history, one place
autogenerate looks, even though these tables are analytics-plane, not audit-plane.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, Float, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from interpose.audit.models import Base


class AuditEntrySynthetic(Base):
    """Section 10.6's "schema-identical structure" to `audit_entries` -- so
    `interpose.analytics.aggregate_telemetry` can point at either table with the same
    query code, parameterized only by table name. Two deliberate exceptions:

    - `prev_hash`/`this_hash` are nullable, unchained placeholders, not a real
      computed hash chain. Tamper-evidence is a property of the *real* audit log;
      computing genuine SHA-256 chain links for 10M rows of fabricated demo data
      would cost real compute for a guarantee nothing downstream ever checks.
    - `parent_id` has no foreign-key constraint (unlike `audit_entries`). The real
      table's FK enforces a parent row exists before a child references it, which
      matters when the *application* is writing rows one at a time in causal order.
      A bulk Spark load has no such ordering guarantee to lean on, and nothing here
      needs referential integrity -- `parent_id` is set to look realistic
      (INTENT/HELD → COMPLETED linkage), not to be enforced.
    """

    __tablename__ = "audit_entries_synthetic"
    __table_args__ = (
        Index("idx_audit_synthetic_agent_time", "agent_id", "timestamp"),
        Index("idx_audit_synthetic_status_time", "status", "timestamp"),
        Index("idx_audit_synthetic_server_tool_time", "server", "tool", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    span_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    server: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    args_hash: Mapped[str] = mapped_column(Text, nullable=False)
    args_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False)
    policies_fired: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decision: Mapped[dict] = mapped_column(JSONB, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    this_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    hitl_ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hitl_reviewer: Mapped[str | None] = mapped_column(Text, nullable=True)
    hitl_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    hitl_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")


# `source` on every aggregate table below is "synthetic" or "real" -- the aggregation
# job can run against either `audit_entries_synthetic` or the genuine `audit_entries`
# (Section 10.6), and dashboards filter/label by it so nobody mistakes fabricated demo
# volume for real gateway traffic.


class TelemetryHourly(Base):
    """Dashboard 1 (Gateway Health) -- approximated from the audit log's own
    `latency_ms`/`status` columns rather than live Prometheus golden signals
    (Section 12.3), since no Prometheus is deployed and nothing exports `/metrics`
    yet (named gap, `concepts/32-synthetic-telemetry-and-postgres-backed-dashboards.md`).
    Real data, just sourced from what's actually running today."""

    __tablename__ = "agg_telemetry_hourly"
    __table_args__ = (
        Index("idx_agg_telemetry_hourly_source_hour", "source", "hour"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    hour: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    server: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    call_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    latency_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p99_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class PolicyFiresDaily(Base):
    """Dashboard 2's "policy fires per policy, by outcome" panel."""

    __tablename__ = "agg_policy_fires_daily"
    __table_args__ = (Index("idx_agg_policy_fires_daily_source_day", "source", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    policy_name: Mapped[str] = mapped_column(Text, nullable=False)
    effect_type: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    fire_count: Mapped[int] = mapped_column(BigInteger, nullable=False)


class HitlDaily(Base):
    """Dashboard 2's HITL queue-depth/response-time/approval-ratio panels."""

    __tablename__ = "agg_hitl_daily"
    __table_args__ = (Index("idx_agg_hitl_daily_source_day", "source", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    reviewer_group: Mapped[str] = mapped_column(Text, nullable=False)
    tickets_created: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approved: Mapped[int] = mapped_column(BigInteger, nullable=False)
    denied: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timed_out: Mapped[int] = mapped_column(BigInteger, nullable=False)
    median_response_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class AmlPackDaily(Base):
    """Dashboard 3 (AML Pack demo-specific)."""

    __tablename__ = "agg_aml_pack_daily"
    __table_args__ = (Index("idx_agg_aml_pack_daily_source_day", "source", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    ofac_calls: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sanctions_matches: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_graph_calls: Mapped[int] = mapped_column(BigInteger, nullable=False)
    structuring_alerts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mark_investigated_denied: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mark_investigated_approved: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Mutually exclusive from `_approved` -- completed with no HITL decision at all.
    # The first version of this aggregation computed a "_pending" column as *every*
    # COMPLETED row, which double-counted with `_approved` (HITL-approved rows are
    # also COMPLETED) -- caught by checking that the three categories should sum to
    # the total and didn't. In the real AML pack, `aml-write-hitl-gate` unconditionally
    # holds every `mark_investigated` call (Phase 3 Day 14), so this bucket would be
    # empty for real traffic; the synthetic generator applies its generic PASS/DENY/
    # HITL outcome mix uniformly across every tool, so a `mark_investigated` row can
    # land in the plain-PASS bucket here even though that can't happen for real.
    mark_investigated_auto_passed: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CostDaily(Base):
    """Dashboard 4 (Cost Telemetry). Populated only from synthetic data -- the real
    gateway has no LLM-cost visibility at all (Phase 3 Day 14's finding); the
    synthetic generator fabricates plausible `tokens`/cost figures for exactly this
    dashboard's benefit, same reasoning Section 10.6 gives for generating synthetic
    telemetry in the first place ("give the Spark analytics-plane demo something
    meaningful to aggregate").

    Grouped by `{day, agent_id, provider}` only -- not also `tool`. The first version
    of the aggregation job did group by tool too and produced 918,819 rows (500
    agents x ~100 tools x 2 providers x 28 days, most combinations with a handful of
    rows each) -- caught by actually looking at the output row count, not assumed
    correct because the query ran without error. A dashboard table with nearly a
    million rows isn't "dashboard-ready" in any useful sense."""

    __tablename__ = "agg_cost_daily"
    __table_args__ = (Index("idx_agg_cost_daily_source_day", "source", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
