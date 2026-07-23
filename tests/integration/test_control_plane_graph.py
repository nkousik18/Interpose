"""Phase 2 Days 6-8 acceptance tests (docs/ROADMAP.md): the full 5-agent graph
routing and behavior, exercised directly against real Postgres, independent of the
gateway's HTTP surface (test_gateway_control_plane.py covers that wiring separately).

No GROQ_API_KEY is set in the test environment, so every LLM-calling agent
(evidence_composer, incident_escalator, and anomaly_detector's optional description)
takes its documented fallback path automatically -- these tests double as proof that
the fallback behavior itself works, not just the happy path.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert

from interpose.audit.chain import GENESIS_HASH, compute_entry_hash
from interpose.audit.db import create_engine, create_session_factory
from interpose.audit.models import AuditEntry
from interpose.config import get_settings
from interpose.control_plane.graph import build_graph
from interpose.control_plane.state import Decision, DecisionEvent, InterposeState, PolicyResult
from interpose.session.redis_client import create_async_redis


async def _seed_session_history(
    session_factory, session_id: str, agent_id: str = "agent-1", n_denials: int = 0, n_rows: int = 5
) -> None:
    """Writes a few real, hash-chained-looking audit rows so the agents' feature
    queries have something real to compute over. Doesn't need to be a genuinely
    valid chain (these tests only read back via SQL, not verify_chain) -- just
    plausible rows with the right agent_id/session_id/status/tool/timestamp."""
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
                "agent_id": agent_id,
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
            for i in range(n_rows)
        ]
        for row in rows:
            row["prev_hash"] = prev_hash
            row["this_hash"] = compute_entry_hash(prev_hash, row)
            prev_hash = row["this_hash"]
            await db_session.execute(insert(AuditEntry).values(**row))


def _event(
    outcome: str,
    audit_id: int = 1,
    session_id: str = "sess-1",
    agent_id: str = "agent-1",
    hitl_ticket_id: UUID | None = None,
) -> DecisionEvent:
    return DecisionEvent(
        audit_id=audit_id,
        trace_id=uuid4(),
        agent_id=agent_id,
        session_id=session_id,
        server="hello-echo",
        tool="echo",
        args_hash="deadbeef",
        policies_fired=[PolicyResult(policy="p1", effect_type="denylist")],
        decision=Decision(outcome=outcome),
        hitl_ticket_id=hitl_ticket_id,
        timestamp=datetime.now(UTC),
    )


def _state(**kwargs: object) -> InterposeState:
    return InterposeState(event=_event(**kwargs))


class _GraphContext:
    def __init__(self) -> None:
        self.engine = create_engine(get_settings().database_url)
        self.session_factory = create_session_factory(self.engine)
        self.redis_conn = create_async_redis(get_settings().redis_url)

    async def __aenter__(self) -> "_GraphContext":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.redis_conn.aclose()
        await self.engine.dispose()

    def build(self):
        return build_graph(self.session_factory, self.redis_conn)


async def _node_sequence(graph, state: InterposeState) -> list[str]:
    return [list(step.keys())[0] async for step in graph.astream(state)]


async def test_pass_with_low_risk_ends_after_policy_evaluator() -> None:
    async with _GraphContext() as ctx:
        await _seed_session_history(ctx.session_factory, "sess-pass", agent_id="agent-pass")
        graph = ctx.build()
        state = _state(outcome="PASS", session_id="sess-pass", agent_id="agent-pass")

        sequence = await _node_sequence(graph, state)
        assert sequence == ["supervisor", "policy_evaluator"]

        result = await graph.ainvoke(state)
        enriched = result.get("enriched")
        assert enriched is not None
        assert enriched.context_features["total_calls"] == 5.0


async def test_pass_with_moderate_risk_reaches_anomaly_detector_which_finds_nothing() -> None:
    async with _GraphContext() as ctx:
        # 2 denials: enough to push A1's risk score over its routing threshold, but
        # under A2's own repeated-denials threshold (3) -- a clean test of routing
        # to a *real* A2 that correctly finds nothing wrong.
        await _seed_session_history(
            ctx.session_factory, "sess-moderate", agent_id="agent-moderate", n_denials=2
        )
        graph = ctx.build()

        sequence = await _node_sequence(
            graph, _state(outcome="PASS", session_id="sess-moderate", agent_id="agent-moderate")
        )
        assert sequence == ["supervisor", "policy_evaluator", "anomaly_detector"]

        result = await graph.ainvoke(
            _state(outcome="PASS", session_id="sess-moderate", agent_id="agent-moderate")
        )
        assert result.get("anomaly") is None


async def test_pass_with_severe_denials_cascades_a2_to_a4() -> None:
    async with _GraphContext() as ctx:
        # 5 denials trips A2's own high-severity repeated-denials rule, which now
        # (Day 8's new third routing hop) cascades onward to A4.
        await _seed_session_history(
            ctx.session_factory, "sess-severe", agent_id="agent-severe", n_denials=5
        )
        graph = ctx.build()

        sequence = await _node_sequence(
            graph, _state(outcome="PASS", session_id="sess-severe", agent_id="agent-severe")
        )
        assert sequence == [
            "supervisor",
            "policy_evaluator",
            "anomaly_detector",
            "incident_escalator",
        ]

        result = await graph.ainvoke(
            _state(outcome="PASS", session_id="sess-severe", agent_id="agent-severe")
        )
        assert result["anomaly"].severity == "high"
        assert result["incident"] is not None
        assert result["incident"].severity == "high"


async def test_hold_routes_through_policy_evaluator_to_evidence_composer() -> None:
    async with _GraphContext() as ctx:
        await _seed_session_history(ctx.session_factory, "sess-hold", agent_id="agent-hold")
        graph = ctx.build()
        ticket_id = uuid4()

        sequence = await _node_sequence(
            graph,
            _state(
                outcome="HOLD",
                session_id="sess-hold",
                agent_id="agent-hold",
                hitl_ticket_id=ticket_id,
            ),
        )
        assert sequence == ["supervisor", "policy_evaluator", "evidence_composer"]

        result = await graph.ainvoke(
            _state(
                outcome="HOLD",
                session_id="sess-hold",
                agent_id="agent-hold",
                hitl_ticket_id=ticket_id,
            )
        )
        packet = result.get("hitl_packet")
        assert packet is not None
        assert packet.ticket_id == ticket_id
        assert packet.recommended_action in ("approve", "deny", "escalate")
        # No GROQ_API_KEY configured in the test environment -- the fallback
        # narrative path, proven here, not the real LLM call.
        assert "manual review required" in packet.narrative


async def test_deny_with_no_repeat_history_reaches_a4_without_promotion() -> None:
    async with _GraphContext() as ctx:
        await _seed_session_history(
            ctx.session_factory, "sess-deny-clean", agent_id="agent-deny-clean"
        )
        graph = ctx.build()

        sequence = await _node_sequence(
            graph, _state(outcome="DENY", session_id="sess-deny-clean", agent_id="agent-deny-clean")
        )
        assert sequence == ["supervisor", "incident_escalator"]

        result = await graph.ainvoke(
            _state(outcome="DENY", session_id="sess-deny-clean", agent_id="agent-deny-clean")
        )
        assert result.get("enriched") is None  # A1 never ran
        assert result.get("incident") is None  # no promotion rule matched


async def test_deny_with_repeat_history_is_promoted_to_an_incident() -> None:
    async with _GraphContext() as ctx:
        await _seed_session_history(
            ctx.session_factory, "sess-deny-repeat", agent_id="agent-deny-repeat", n_denials=3
        )
        graph = ctx.build()

        result = await graph.ainvoke(
            _state(outcome="DENY", session_id="sess-deny-repeat", agent_id="agent-deny-repeat")
        )
        incident = result.get("incident")
        assert incident is not None
        assert incident.severity == "med"
        assert incident.recommended_response == "investigate"  # the fallback's default
