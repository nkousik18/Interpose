"""Unit tests for Agent A2's deterministic core (Section 7.8): the rate-based
z-score and the repeated-denials rule, as pure functions over synthetic signals --
no database needed. `compute_anomaly_signals` (the live-query half) is exercised
against a real Postgres in tests/integration/test_control_plane_graph.py instead.
"""

from datetime import UTC, datetime
from uuid import uuid4

from interpose.control_plane.agents.anomaly_detector import (
    AnomalySignals,
    compute_rate_zscore,
    detect_anomaly,
)
from interpose.control_plane.state import Decision, DecisionEvent


def _event() -> DecisionEvent:
    return DecisionEvent(
        audit_id=1,
        trace_id=uuid4(),
        agent_id="agent-1",
        session_id="sess-1",
        server="hello-echo",
        tool="echo",
        args_hash="deadbeef",
        policies_fired=[],
        decision=Decision(outcome="PASS"),
        timestamp=datetime.now(UTC),
    )


def _signals(current: int = 0, prior: list[int] | None = None, denials: int = 0) -> AnomalySignals:
    return AnomalySignals(
        current_window_calls=current,
        prior_window_call_counts=prior or [],
        denials_last_15_min=denials,
    )


class TestComputeRateZscore:
    def test_returns_none_with_insufficient_history(self) -> None:
        assert compute_rate_zscore(_signals(current=10, prior=[1, 2])) is None

    def test_returns_none_when_history_has_zero_variance(self) -> None:
        # stdev == 0 would be a division by zero -- must return None, not crash.
        assert compute_rate_zscore(_signals(current=50, prior=[5, 5, 5, 5])) is None

    def test_computes_a_real_zscore_with_enough_varied_history(self) -> None:
        zscore = compute_rate_zscore(_signals(current=50, prior=[2, 3, 4, 3, 2, 3]))
        assert zscore is not None
        assert zscore > 0  # current is far above this history's mean

    def test_negative_zscore_for_a_quiet_window(self) -> None:
        zscore = compute_rate_zscore(_signals(current=0, prior=[10, 12, 11, 9, 10]))
        assert zscore is not None
        assert zscore < 0


class TestDetectAnomaly:
    def test_no_signal_no_flag(self) -> None:
        assert detect_anomaly(_signals(current=3, prior=[3, 3, 3, 3]), _event()) is None

    def test_rate_spike_flagged_when_zscore_exceeds_threshold(self) -> None:
        flag = detect_anomaly(_signals(current=100, prior=[2, 3, 2, 3, 2]), _event())
        assert flag is not None
        assert flag.anomaly_type == "rate_spike"

    def test_rate_spike_severity_high_for_extreme_zscore(self) -> None:
        # Prior history needs *some* variance (stdev != 0) for a z-score to exist
        # at all -- all-identical values would make every window "normal" by
        # definition, no matter how extreme the current one is.
        flag = detect_anomaly(_signals(current=1000, prior=[1, 2, 1, 2, 1]), _event())
        assert flag is not None
        assert flag.severity == "high"

    def test_repeated_denials_flagged_at_threshold(self) -> None:
        flag = detect_anomaly(_signals(current=1, prior=[1, 1, 1], denials=3), _event())
        assert flag is not None
        assert flag.anomaly_type == "repeated_denials"

    def test_repeated_denials_below_threshold_not_flagged(self) -> None:
        assert detect_anomaly(_signals(current=1, prior=[1, 1, 1], denials=2), _event()) is None

    def test_repeated_denials_severity_high_at_high_count(self) -> None:
        flag = detect_anomaly(_signals(current=1, prior=[1, 1, 1], denials=5), _event())
        assert flag is not None
        assert flag.severity == "high"

    def test_repeated_denials_severity_med_below_high_threshold(self) -> None:
        flag = detect_anomaly(_signals(current=1, prior=[1, 1, 1], denials=3), _event())
        assert flag is not None
        assert flag.severity == "med"

    def test_rate_spike_takes_priority_over_repeated_denials(self) -> None:
        # Both strategies could fire in principle -- rate-based is checked first.
        flag = detect_anomaly(
            _signals(current=1000, prior=[1, 2, 1, 2, 1], denials=5), _event()
        )
        assert flag is not None
        assert flag.anomaly_type == "rate_spike"

    def test_flag_carries_the_triggering_event(self) -> None:
        event = _event()
        flag = detect_anomaly(_signals(current=1, prior=[1, 1, 1], denials=3), event)
        assert flag is not None
        assert flag.event == event
