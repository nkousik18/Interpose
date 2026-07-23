"""Unit tests for Agent A1's pure risk-score heuristic (Section 7.7). The DB-backed
`compute_context_features` is tested against a real Postgres in
tests/integration/test_control_plane_graph.py instead -- it's not meaningfully
testable without one.
"""

from interpose.control_plane.agents.policy_evaluator import compute_session_risk_score


def _features(**overrides: float) -> dict[str, float]:
    base = {
        "calls_per_minute": 0.0,
        "unique_tools_count": 0.0,
        "total_calls": 0.0,
        "hitl_ticket_count": 0.0,
        "denial_count": 0.0,
    }
    base.update(overrides)
    return base


def test_all_zero_features_score_zero() -> None:
    assert compute_session_risk_score(_features()) == 0.0


def test_score_is_clipped_to_one() -> None:
    score = compute_session_risk_score(
        _features(calls_per_minute=1000, denial_count=50, hitl_ticket_count=50)
    )
    assert score == 1.0


def test_score_is_never_negative() -> None:
    # Defensive: even if a caller somehow passed negative counts, the score should
    # still land in [0, 1], not go negative.
    score = compute_session_risk_score(_features(calls_per_minute=-10))
    assert score >= 0.0


def test_a_denial_outweighs_a_little_ordinary_call_volume() -> None:
    modestly_busy_but_clean = compute_session_risk_score(_features(calls_per_minute=2))
    one_denial = compute_session_risk_score(_features(denial_count=1))
    assert one_denial > modestly_busy_but_clean


def test_denial_contribution_caps_at_three() -> None:
    three_denials = compute_session_risk_score(_features(denial_count=3))
    ten_denials = compute_session_risk_score(_features(denial_count=10))
    assert three_denials == ten_denials
