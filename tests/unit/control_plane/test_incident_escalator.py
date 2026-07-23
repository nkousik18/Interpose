"""Unit tests for Agent A4's promotion rules (Section 7.10) as a pure function --
no database needed. `compute_incident_signals` (the live-query half) is exercised
against a real Postgres in tests/integration/test_control_plane_graph.py instead.
"""

from datetime import UTC, datetime
from uuid import uuid4

from interpose.control_plane.agents.incident_escalator import (
    IncidentSignals,
    compute_incident_severity,
    should_promote,
)
from interpose.control_plane.state import (
    AnomalyFlag,
    Decision,
    DecisionEvent,
    EnrichedDecision,
    InterposeState,
)


def _event(outcome: str = "DENY") -> DecisionEvent:
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


def _state(
    outcome: str = "DENY",
    anomaly_severity: str | None = None,
    risk_score: float | None = None,
) -> InterposeState:
    event = _event(outcome)
    anomaly = None
    if anomaly_severity is not None:
        anomaly = AnomalyFlag(
            event=event, anomaly_type="rate_spike", severity=anomaly_severity, evidence={}
        )
    enriched = None
    if risk_score is not None:
        enriched = EnrichedDecision(event=event, context_features={}, session_risk_score=risk_score)
    return InterposeState(event=event, anomaly=anomaly, enriched=enriched)


class TestShouldPromote:
    def test_no_signals_no_promotion(self) -> None:
        assert should_promote(_state(), IncidentSignals(denials_last_15_min=0)) is None

    def test_repeated_denials_promotes(self) -> None:
        rule = should_promote(_state(), IncidentSignals(denials_last_15_min=3))
        assert rule == "repeated_denials"

    def test_denials_below_threshold_does_not_promote(self) -> None:
        rule = should_promote(_state(), IncidentSignals(denials_last_15_min=2))
        assert rule is None

    def test_high_severity_anomaly_promotes(self) -> None:
        state = _state(outcome="PASS", anomaly_severity="high")
        rule = should_promote(state, IncidentSignals(denials_last_15_min=0))
        assert rule == "high_severity_anomaly"

    def test_medium_severity_anomaly_does_not_promote(self) -> None:
        state = _state(outcome="PASS", anomaly_severity="med")
        rule = should_promote(state, IncidentSignals(denials_last_15_min=0))
        assert rule is None

    def test_high_risk_pending_hitl_promotes(self) -> None:
        state = _state(outcome="HOLD", risk_score=0.9)
        rule = should_promote(state, IncidentSignals(denials_last_15_min=0))
        assert rule == "high_risk_pending_hitl"

    def test_high_risk_without_pending_hitl_does_not_promote(self) -> None:
        # risk > 0.8 but outcome isn't HOLD -- nothing is actually pending review.
        state = _state(outcome="PASS", risk_score=0.9)
        rule = should_promote(state, IncidentSignals(denials_last_15_min=0))
        assert rule is None

    def test_risk_at_or_below_threshold_does_not_promote(self) -> None:
        state = _state(outcome="HOLD", risk_score=0.8)
        rule = should_promote(state, IncidentSignals(denials_last_15_min=0))
        assert rule is None

    def test_repeated_denials_checked_before_anomaly_severity(self) -> None:
        state = _state(outcome="PASS", anomaly_severity="high")
        rule = should_promote(state, IncidentSignals(denials_last_15_min=5))
        assert rule == "repeated_denials"


class TestComputeIncidentSeverity:
    def test_high_severity_anomaly_rule_is_high(self) -> None:
        assert compute_incident_severity("high_severity_anomaly", _state()) == "high"

    def test_high_risk_pending_hitl_rule_is_high(self) -> None:
        assert compute_incident_severity("high_risk_pending_hitl", _state()) == "high"

    def test_plain_repeated_denials_is_med(self) -> None:
        assert compute_incident_severity("repeated_denials", _state()) == "med"

    def test_repeated_denials_upgraded_to_high_with_a_co_occurring_high_anomaly(self) -> None:
        # The exact scenario that surfaced this: should_promote reports
        # "repeated_denials" (checked first) even when a high-severity anomaly is
        # also present -- severity must still reflect the anomaly.
        state = _state(outcome="PASS", anomaly_severity="high")
        assert compute_incident_severity("repeated_denials", state) == "high"

    def test_repeated_denials_stays_med_with_a_medium_anomaly(self) -> None:
        state = _state(outcome="PASS", anomaly_severity="med")
        assert compute_incident_severity("repeated_denials", state) == "med"
