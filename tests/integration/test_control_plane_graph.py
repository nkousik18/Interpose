"""Phase 2 Day 6 acceptance test (docs/ROADMAP.md): "A0 routes; A1 enriches" --
exercised directly against the compiled LangGraph graph and a real Postgres audit
log, independent of the gateway's HTTP surface (test_gateway_control_plane.py covers
the full gateway-to-control-plane wiring separately).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import insert

from interpose.audit.chain import GENESIS_HASH, compute_entry_hash
from interpose.audit.db import create_engine, create_session_factory
from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.control_plane.graph import build_graph
from interpose.control_plane.state import Decision, DecisionEvent, InterposeState, PolicyResult
from interpose.session.redis_client import create_async_redis


async def _seed_session_history(session_factory, session_id: str, n_denials: int = 0) -> None:
    """Writes a few real, hash-chained-looking audit rows for `session_id` so A1's
    feature queries have something real to compute over. Doesn't need to be a
    genuinely valid chain (this test only reads back via SQL, not verify_chain) --
    just plausible rows with the right session_id/status/tool/timestamp."""
    async with session_factory() as db_session, db_session.begin():
        prev_hash = GENESIS_HASH
        now = datetime.now(UTC)
        rows = [
            {
                "trace_id": uuid4(),
                "span_id": uuid4(),
                "parent_id": None,
                "timestamp": now - timedelta(seconds=i),
                "status": "DENIED" if i < n_denials else "COMPLETED",
                "agent_id": "agent-1",
                "session_id": session_id,
                "server": "hello-echo",
                "tool": "echo",
                "args_hash": "deadbeef",
                "args_redacted": {},
                "policies_fired": [],
                "decision": {"outcome": "DENY" if i < n_denials else "PASS"},
                "latency_ms": None,
                "tokens": None,
                "hitl_ticket_id": None,
                "hitl_reviewer": None,
                "hitl_decision": None,
                "hitl_rationale": None,
            }
            for i in range(5)
        ]
        for row in rows:
            row["prev_hash"] = prev_hash
            row["this_hash"] = compute_entry_hash(prev_hash, row)
            prev_hash = row["this_hash"]
            await db_session.execute(insert(AuditEntry).values(**row))


def _event(outcome: str, audit_id: int = 1, session_id: str = "sess-1") -> DecisionEvent:
    return DecisionEvent(
        audit_id=audit_id,
        trace_id=uuid4(),
        agent_id="agent-1",
        session_id=session_id,
        server="hello-echo",
        tool="echo",
        args_hash="deadbeef",
        policies_fired=[PolicyResult(policy="p1", effect_type="denylist")],
        decision=Decision(outcome=outcome),
        timestamp=datetime.now(UTC),
    )


def _state(outcome: str, audit_id: int = 1, session_id: str = "sess-1") -> InterposeState:
    return InterposeState(event=_event(outcome, audit_id=audit_id, session_id=session_id))


async def test_pass_routes_through_supervisor_and_policy_evaluator_to_end() -> None:
    engine = create_engine(get_settings().database_url)
    session_factory = create_session_factory(engine)
    redis_conn = create_async_redis(get_settings().redis_url)
    try:
        await _seed_session_history(session_factory, "sess-pass")
        graph = build_graph(session_factory, redis_conn)

        node_sequence = [
            list(step.keys())[0]
            async for step in graph.astream(_state("PASS", session_id="sess-pass"))
        ]
        assert node_sequence == ["supervisor", "policy_evaluator"]

        result = await graph.ainvoke(_state("PASS", session_id="sess-pass"))
        enriched = result.get("enriched")
        assert enriched is not None
        assert enriched.context_features["total_calls"] == 5.0
    finally:
        await redis_conn.aclose()
        await engine.dispose()


async def test_hold_routes_through_policy_evaluator_to_evidence_composer_stub() -> None:
    engine = create_engine(get_settings().database_url)
    session_factory = create_session_factory(engine)
    redis_conn = create_async_redis(get_settings().redis_url)
    try:
        await _seed_session_history(session_factory, "sess-hold")
        graph = build_graph(session_factory, redis_conn)

        node_sequence = [
            list(step.keys())[0]
            async for step in graph.astream(_state("HOLD", session_id="sess-hold"))
        ]
        assert node_sequence == ["supervisor", "policy_evaluator", "evidence_composer_stub"]
    finally:
        await redis_conn.aclose()
        await engine.dispose()


async def test_deny_routes_straight_to_incident_escalator_stub_skipping_a1() -> None:
    engine = create_engine(get_settings().database_url)
    session_factory = create_session_factory(engine)
    redis_conn = create_async_redis(get_settings().redis_url)
    try:
        await _seed_session_history(session_factory, "sess-deny")
        graph = build_graph(session_factory, redis_conn)

        node_sequence = [
            list(step.keys())[0]
            async for step in graph.astream(_state("DENY", session_id="sess-deny"))
        ]
        assert node_sequence == ["supervisor", "incident_escalator_stub"]

        result = await graph.ainvoke(_state("DENY", session_id="sess-deny"))
        assert result.get("enriched") is None  # A1 never ran
    finally:
        await redis_conn.aclose()
        await engine.dispose()


async def test_many_denials_push_pass_over_the_risk_threshold_to_anomaly_detector() -> None:
    engine = create_engine(get_settings().database_url)
    session_factory = create_session_factory(engine)
    redis_conn = create_async_redis(get_settings().redis_url)
    try:
        # 5 rows, all DENIED -- pushes session_risk_score above the routing threshold.
        await _seed_session_history(session_factory, "sess-risky", n_denials=5)
        graph = build_graph(session_factory, redis_conn)

        node_sequence = [
            list(step.keys())[0]
            async for step in graph.astream(_state("PASS", session_id="sess-risky"))
        ]
        assert node_sequence == ["supervisor", "policy_evaluator", "anomaly_detector_stub"]
    finally:
        await redis_conn.aclose()
        await engine.dispose()
