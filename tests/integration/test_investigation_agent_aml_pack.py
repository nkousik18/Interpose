"""Phase 3 Day 14 acceptance test (docs/ROADMAP.md): the real AML policy pack
(policies/packs/aml/) fires at its expected trigger points against a real gateway +
real ofac-sanctions + real transaction-graph servers (fixture data,
`aml_pack_investigator_stack` in conftest.py) -- sanctions-required denies
out-of-order calls but never `get_account`, the write HITL gate holds
`mark_investigated`, structuring-alert tags an incident and sets a session flag, and
audit-tagging labels every governed call.

Two real bugs found live while building this test, not assumed from the protocol
docs: (1) `Mcp-Session-Id` is assigned independently by *each* upstream server, so it
can't correlate a sanctions check on one server with a query on another --
`aml-sanctions-required` had to be redesigned around `agent_id` instead (see
`interpose.policies.custom.RequestPolicyContext`'s docstring). (2) FastMCP's
streamable-HTTP transport responds `text/event-stream` (SSE-framed), never bare
`application/json`, for every `tools/call` -- the gateway's buffered response path
(`interpose.gateway.app._decode_mcp_body`/`_encode_mcp_body`) failed outright against
a live server until this was handled.
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import create_engine, select

from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.session import hitl
from interpose.session.redis_client import create_sync_redis

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "agents" / "aml-investigator" / "src"))

from aml_investigator.gateway_client import InvestigationClient, ToolCallError  # noqa: E402

GATEWAY_URL = "http://127.0.0.1:8000"


def _fetch_entries_for_agent(agent_id: str) -> list[dict]:
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(AuditEntry)
                .where(AuditEntry.agent_id == agent_id)
                .order_by(AuditEntry.id)
            ).all()
            columns = [c.name for c in AuditEntry.__table__.columns]
            return [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        engine.dispose()


async def _approve_shortly(reviewer: str = "alice") -> None:
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
                    rationale="reviewed for the test",
                )
                return
            await asyncio.sleep(0.1)
        raise TimeoutError("no pending HITL ticket appeared in time")
    finally:
        conn.close()


async def test_transaction_graph_call_denied_without_a_prior_sanctions_check(
    aml_pack_investigator_stack: None,
) -> None:
    async with InvestigationClient(GATEWAY_URL) as client:
        try:
            await client.neighbors("1:ACC001")
            raise AssertionError("expected neighbors to be denied")
        except ToolCallError as exc:
            assert "sanctions" in str(exc).lower()


async def test_get_account_is_not_gated_by_the_sanctions_precondition(
    aml_pack_investigator_stack: None,
) -> None:
    # get_account must stay ungated: it's the only source of the entity name
    # check_entity needs, so gating it too would make the precondition
    # unsatisfiable (see policies/packs/aml/aml-sanctions-required.yaml).
    async with InvestigationClient(GATEWAY_URL) as client:
        account = await client.get_account("1:ACC001")
        assert account["entity_name"] == "Suspect Corp"


async def test_transaction_graph_call_allowed_after_a_sanctions_check(
    aml_pack_investigator_stack: None,
) -> None:
    async with InvestigationClient(GATEWAY_URL) as client:
        account = await client.get_account("1:ACC001")
        await client.check_entity(account["entity_name"], entity_type="entity")
        neighbors = await client.neighbors("1:ACC001")
        assert neighbors  # didn't raise, and the fixture graph has real neighbors


async def test_structuring_alert_tags_the_incident_and_sets_the_session_flag(
    aml_pack_investigator_stack: None,
) -> None:
    async with InvestigationClient(GATEWAY_URL) as client:
        account = await client.get_account("1:ACC001")
        await client.check_entity(account["entity_name"], entity_type="entity")
        signal = await client.structuring_check("1:ACC001")
        assert signal["flagged"] is True

        entries = _fetch_entries_for_agent(client.agent_id)
        structuring_entry = next(
            e for e in entries if e["tool"] == "structuring_check" and e["status"] == "COMPLETED"
        )
        assert "incident:structuring" in structuring_entry["tags"]
        assert "severity:high" in structuring_entry["tags"]

        redis_conn = create_sync_redis(get_settings().redis_url)
        try:
            # session_id here is transaction-graph's own -- the one the flag is
            # actually keyed on (aml_structuring_alert runs at Stage 8, on the same
            # request/response whose session_id it was given).
            tg_session_id = next(
                e["session_id"] for e in entries if e["tool"] == "structuring_check"
            )
            flag = redis_conn.get(f"interpose:session:{tg_session_id}:force_hitl")
            assert flag == "aml_structuring_alert"
        finally:
            redis_conn.close()


async def test_every_governed_call_is_tagged_pack_aml(
    aml_pack_investigator_stack: None,
) -> None:
    async with InvestigationClient(GATEWAY_URL) as client:
        await client.get_account("1:ACC001")

        entries = _fetch_entries_for_agent(client.agent_id)
        assert entries
        for entry in entries:
            assert "pack:aml" in entry["tags"]
            assert "regulation:BSA" in entry["tags"]


async def test_mark_investigated_holds_and_completes_once_approved(
    aml_pack_investigator_stack: None,
) -> None:
    async with InvestigationClient(GATEWAY_URL) as client:
        account = await client.get_account("1:ACC001")
        await client.check_entity(account["entity_name"], entity_type="entity")

        write_result, _ = await asyncio.gather(
            client.mark_investigated("1:ACC001", "escalate", "structuring pattern confirmed"),
            _approve_shortly(),
        )
        assert write_result["disposition"] == "escalate"

        entries = _fetch_entries_for_agent(client.agent_id)
        held = next(
            e for e in entries if e["tool"] == "mark_investigated" and e["status"] == "HELD"
        )
        completed = next(
            e for e in entries if e["tool"] == "mark_investigated" and e["status"] == "COMPLETED"
        )
        assert completed["parent_id"] == held["id"]
        assert completed["hitl_decision"] == "APPROVED"
