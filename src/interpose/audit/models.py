"""SQLAlchemy models for the audit store (docs/INTERPOSE_SCOPING.md Section 6.7).

One call produces either one row (a terminal decision made before any upstream call
happened -- DENIED, or later HELD) or two linked rows (PASS: an INTENT row written
before forwarding, a COMPLETED/UPSTREAM_ERROR row written after, linked by
`parent_id`). Two rows rather than one updated in place because the audit log is
append-only end to end (Section 10.7: the writer role gets INSERT only, no UPDATE or
DELETE) -- there is no in-place status transition to make.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

STATUSES = ("INTENT", "COMPLETED", "DENIED", "HELD", "UPSTREAM_ERROR")
_STATUS_CHECK_SQL = "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")"


class Base(DeclarativeBase):
    pass


class AuditEntry(Base):
    __tablename__ = "audit_entries"
    __table_args__ = (
        CheckConstraint(_STATUS_CHECK_SQL, name="ck_audit_entries_status"),
        Index("idx_audit_trace", "trace_id"),
        Index("idx_audit_agent_time", "agent_id", "timestamp"),
        Index("idx_audit_status_time", "status", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    span_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audit_entries.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
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
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False)
    this_hash: Mapped[str] = mapped_column(Text, nullable=False)
    hitl_ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hitl_reviewer: Mapped[str | None] = mapped_column(Text, nullable=True)
    hitl_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    hitl_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
