"""Unit tests for Agent A0 -- Supervisor routing (Section 7.6): a matrix of decision
types (and, for the second hop, risk scores) to expected routes. 20+ cases per the
scoping doc's own testing spec for this agent.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from interpose.control_plane.agents.supervisor import (
    RISK_THRESHOLD,
    route_after_policy_evaluator,
    route_after_supervisor,
)
from interpose.control_plane.state import Decision, DecisionEvent, EnrichedDecision, InterposeState


def _event(outcome: str) -> DecisionEvent:
    return DecisionEvent(
        audit_id=1,
        trace_id=uuid4(),
        agent_id="agent-1",
        session_id="sess-1",
        server="hello-echo",
        tool="echo",
        args_hash="deadbeef",
        policies_fired=[],
        decision=Decision(outcome=outcome),
        timestamp=datetime.now(UTC),
    )


def _state(outcome: str, risk_score: float | None = None) -> InterposeState:
    event = _event(outcome)
    enriched = None
    if risk_score is not None:
        enriched = EnrichedDecision(event=event, context_features={}, session_risk_score=risk_score)
    return InterposeState(event=event, enriched=enriched)


class TestRouteAfterSupervisor:
    @pytest.mark.parametrize("outcome", ["DENY"])
    def test_deny_routes_to_a4(self, outcome: str) -> None:
        assert route_after_supervisor(_state(outcome)) == "to_a4"

    @pytest.mark.parametrize("outcome", ["PASS", "HOLD", "UNKNOWN", ""])
    def test_everything_else_routes_to_a1(self, outcome: str) -> None:
        assert route_after_supervisor(_state(outcome)) == "to_a1"


class TestRouteAfterPolicyEvaluator:
    @pytest.mark.parametrize("risk_score", [0.0, 0.1, 0.3, 0.5, 0.9, 1.0])
    def test_hold_always_routes_to_a3_regardless_of_risk(self, risk_score: float) -> None:
        assert route_after_policy_evaluator(_state("HOLD", risk_score)) == "to_a3"

    def test_hold_routes_to_a3_even_with_no_enrichment(self) -> None:
        assert route_after_policy_evaluator(_state("HOLD", None)) == "to_a3"

    @pytest.mark.parametrize("risk_score", [0.0, 0.1, 0.25, 0.49, RISK_THRESHOLD])
    def test_pass_at_or_below_threshold_ends(self, risk_score: float) -> None:
        assert route_after_policy_evaluator(_state("PASS", risk_score)) == "end"

    @pytest.mark.parametrize("risk_score", [0.51, 0.6, 0.75, 0.9, 1.0])
    def test_pass_above_threshold_routes_to_a2(self, risk_score: float) -> None:
        assert route_after_policy_evaluator(_state("PASS", risk_score)) == "to_a2"

    def test_pass_with_no_enrichment_ends_rather_than_crashing(self) -> None:
        assert route_after_policy_evaluator(_state("PASS", None)) == "end"

    @pytest.mark.parametrize("risk_score", [0.0, 0.6, 1.0])
    def test_deny_reaching_this_router_directly_still_ends(self, risk_score: float) -> None:
        # DENY never reaches this router in the real graph (Supervisor already sent
        # it straight to A4) -- but the pure function itself should still behave
        # sanely if called directly, rather than assuming its caller's invariants.
        assert route_after_policy_evaluator(_state("DENY", risk_score)) == "end"
