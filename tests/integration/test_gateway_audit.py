"""Phase 1, Day 4 acceptance test (docs/ROADMAP.md): a real call through the live
gateway produces real, hash-chained rows in a real Postgres audit_entries table
(Stage 6 / Stage 8, docs/INTERPOSE_SCOPING.md Section 6.5 / 6.7), and tampering with a
stored row is detectable -- the adversarial check G3 calls for.
"""

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from sqlalchemy import create_engine, select, text

from interpose.audit.chain import verify_chain
from interpose.audit.models import AuditEntry
from interpose.config import get_settings

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


async def test_passed_call_produces_linked_intent_and_completed_rows(
    upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("echo", {"text": "audit me"})

    entries = _fetch_all_entries()
    assert len(entries) == 2
    intent, completed = entries
    assert intent["status"] == "INTENT"
    assert intent["parent_id"] is None
    assert completed["status"] == "COMPLETED"
    assert completed["parent_id"] == intent["id"]
    assert intent["trace_id"] == completed["trace_id"]
    assert intent["tool"] == "echo"
    assert intent["args_redacted"] == {"text": "audit me"}

    assert verify_chain(entries).valid


async def test_denied_call_produces_a_single_denied_row(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            with pytest.raises(McpError):
                await session.call_tool("dangerous_tool", {})

    entries = _fetch_all_entries()
    assert len(entries) == 1
    assert entries[0]["status"] == "DENIED"
    assert entries[0]["parent_id"] is None
    assert entries[0]["decision"]["fired_policy"] == "hello-echo-no-dangerous-tool"

    assert verify_chain(entries).valid


async def test_tampering_with_a_stored_row_is_detected(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("echo", {"text": "before tampering"})

    engine = create_engine(get_settings().database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_entries SET tool = 'tampered_tool' WHERE id = 1"))
    finally:
        engine.dispose()

    result = verify_chain(_fetch_all_entries())
    assert not result.valid
    assert result.first_mismatch_id == 1
