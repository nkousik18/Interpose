"""Agent A0 -- Supervisor (docs/INTERPOSE_SCOPING.md Section 7.6).

Pure rule-based dispatch. Not an LLM, not a "thinking" agent -- routing decisions
need to be deterministic and fast (Section 7.6: "Supervisor decisions must be
deterministic and fast. LLMs are inappropriate here.").

The routing rule is a two-hop sequence, not a single fan-out choice, matching Section
7.6's prose exactly:
  - HOLD  -> A1, then (after enrichment) -> A3
  - DENY  -> A4 directly, skipping A1 entirely
  - PASS with session risk above threshold -> A1, then -> A2
  - PASS otherwise -> A1, then END

A third hop, added Phase 2 Day 8 once Agent A2 does real work: after A2 runs, a
high-severity AnomalyFlag promotes onward to A4 (Section 7.10's "AnomalyFlag severity
== high -> promote" rule) -- otherwise the graph ends there, same as before. This is
the only one of Section 7.10's four promotion triggers that's actually reachable via
the graph today; see `interpose.control_plane.agents.incident_escalator`'s module
docstring for the one that isn't yet (risk > 0.8 with pending HITL, via Agent A3).

Separate router functions implement each hop, since LangGraph's
`add_conditional_edges` dispatches from one node at a time based on the state as it
exists *after* that node runs -- `route_after_supervisor` runs before A1 has had a
chance to enrich anything, `route_after_policy_evaluator` runs after, and
`route_after_anomaly_detector` runs after A2.
"""

from __future__ import annotations

from interpose.control_plane.state import InterposeState

# Placeholder pending real calibration -- there's no historical baseline data yet to
# set this against (see interpose.control_plane.agents.policy_evaluator). Revisit
# once Section 6.10's Spark aggregation job or enough production traffic exists.
RISK_THRESHOLD = 0.5


def route_after_supervisor(state: InterposeState) -> str:
    """First hop. DENY skips straight to A4; everything else goes through A1."""
    if state.event.decision.outcome == "DENY":
        return "to_a4"
    return "to_a1"


def route_after_policy_evaluator(state: InterposeState) -> str:
    """Second hop, after A1 has enriched (or been skipped -- but this router only
    runs on the path where A1 did run, so `state.enriched` is always set here)."""
    if state.event.decision.outcome == "HOLD":
        return "to_a3"
    if (
        state.event.decision.outcome == "PASS"
        and state.enriched is not None
        and state.enriched.session_risk_score > RISK_THRESHOLD
    ):
        return "to_a2"
    return "end"


def route_after_anomaly_detector(state: InterposeState) -> str:
    """Third hop, after A2 has run. A high-severity flag promotes onward to A4;
    anything else (no flag, or a lower-severity one) ends the graph here."""
    if state.anomaly is not None and state.anomaly.severity == "high":
        return "to_a4"
    return "end"
