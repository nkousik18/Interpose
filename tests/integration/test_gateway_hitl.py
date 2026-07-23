"""Phase 2 Day 6 acceptance test (docs/ROADMAP.md): the full HITL cycle through the
live gateway -- a held call, reviewed via the real `interpose.session.hitl` ticket
queue (Redis), approved/denied/timed-out, with the resulting audit trail linked back
to the HELD entry via `parent_id` (Section 6.5 Stage 5/7, Section 6.8).
"""

import asyncio

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from sqlalchemy import create_engine, select

from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.session import hitl
from interpose.session.redis_client import create_sync_redis

GATEWAY_URL = "http://127.0.0.1:8000/mcp/hello-echo"


def _fetch_all_entries() -> list[dict]:
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(select(AuditEntry).order_by(AuditEntry.id)).all()
            columns = [c.name for c in AuditEntry.__table__.columns]
            return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        engine.dispose()


async def _approve_shortly(reviewer: str = "alice", rationale: str = "looks fine") -> None:
    """Waits for a pending ticket to show up, then approves the first one it finds --
    simulates a reviewer running `interpose review approve` while the call is held."""
    conn = create_sync_redis(get_settings().redis_url)
    try:
        for _ in range(50):  # up to ~5s
            pending = hitl.list_pending(conn)
            if pending:
                hitl.decide_ticket(
                    conn,
                    pending[0].ticket_id,
                    status="APPROVED",
                    decided_by=reviewer,
                    rationale=rationale,
                )
                return
            await asyncio.sleep(0.1)
        raise TimeoutError("no pending HITL ticket appeared in time")
    finally:
        conn.close()


async def _deny_shortly(reviewer: str = "bob", rationale: str = "too risky") -> None:
    conn = create_sync_redis(get_settings().redis_url)
    try:
        for _ in range(50):
            pending = hitl.list_pending(conn)
            if pending:
                hitl.decide_ticket(
                    conn,
                    pending[0].ticket_id,
                    status="DENIED",
                    decided_by=reviewer,
                    rationale=rationale,
                )
                return
            await asyncio.sleep(0.1)
        raise TimeoutError("no pending HITL ticket appeared in time")
    finally:
        conn.close()


async def test_approved_hold_forwards_and_records_full_audit_trail(
    upstream_and_gateway: None,
) -> None:
    async def make_call() -> str:
        async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("hitl_tool", {})
                return result.content[0].text

    call_result, _ = await asyncio.gather(make_call(), _approve_shortly())
    assert call_result == "approved and executed"

    entries = _fetch_all_entries()
    assert len(entries) == 2
    held, completed = entries
    assert held["status"] == "HELD"
    assert held["parent_id"] is None
    assert completed["status"] == "COMPLETED"
    assert completed["parent_id"] == held["id"]
    assert completed["hitl_reviewer"] == "alice"
    assert completed["hitl_decision"] == "APPROVED"
    assert completed["hitl_rationale"] == "looks fine"
    assert completed["hitl_ticket_id"] is not None


async def test_denied_hold_never_forwards(upstream_and_gateway: None) -> None:
    async def make_call() -> None:
        async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                with pytest.raises(McpError) as exc_info:
                    await session.call_tool("hitl_tool", {})
                assert exc_info.value.error.message == "hitl_denied"
                assert exc_info.value.error.data["reviewer"] == "bob"

    await asyncio.gather(make_call(), _deny_shortly())

    entries = _fetch_all_entries()
    assert len(entries) == 2
    held, denied = entries
    assert held["status"] == "HELD"
    assert denied["status"] == "DENIED"
    assert denied["parent_id"] == held["id"]
    assert denied["hitl_reviewer"] == "bob"
    assert denied["hitl_decision"] == "DENIED"
    assert denied["hitl_rationale"] == "too risky"


async def test_hold_with_no_reviewer_times_out_and_denies(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            with pytest.raises(McpError) as exc_info:
                await session.call_tool("hitl_timeout_tool", {})
            assert exc_info.value.error.message == "hitl_timeout"

    entries = _fetch_all_entries()
    assert len(entries) == 2
    held, denied = entries
    assert held["status"] == "HELD"
    assert denied["status"] == "DENIED"
    assert denied["decision"]["reason"] == "hitl_timeout"
    assert denied["hitl_reviewer"] is None
