"""Builds the LangGraph control-plane graph (docs/INTERPOSE_SCOPING.md Section 7.5).

Supervisor (A0) and Policy Evaluator (A1) are real. Anomaly Detector (A2), Evidence
Composer (A3), and Incident Escalator (A4) are placeholder terminal nodes
(`interpose.control_plane.agents.stubs`) until Phase 2 Day 8 -- the routing *to* them
is real and tested; their actual behavior isn't built yet.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.control_plane.agents.policy_evaluator import make_policy_evaluator_node
from interpose.control_plane.agents.stubs import make_stub_node
from interpose.control_plane.agents.supervisor import (
    route_after_policy_evaluator,
    route_after_supervisor,
)
from interpose.control_plane.state import InterposeState


async def _supervisor_node(state: InterposeState) -> dict:
    """A0 itself does no work on state -- Section 7.6: pure dispatch. Routing
    happens via the conditional-edge functions LangGraph calls separately; this node
    only exists to give the graph an explicit, nameable entry point to route from."""
    return {}


def build_graph(
    session_factory: async_sessionmaker, redis_conn: Redis
) -> CompiledStateGraph:
    graph: StateGraph = StateGraph(InterposeState)

    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("policy_evaluator", make_policy_evaluator_node(session_factory, redis_conn))
    graph.add_node("anomaly_detector_stub", make_stub_node("A2"))
    graph.add_node("evidence_composer_stub", make_stub_node("A3"))
    graph.add_node("incident_escalator_stub", make_stub_node("A4"))

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"to_a1": "policy_evaluator", "to_a4": "incident_escalator_stub"},
    )
    graph.add_conditional_edges(
        "policy_evaluator",
        route_after_policy_evaluator,
        {"to_a2": "anomaly_detector_stub", "to_a3": "evidence_composer_stub", "end": END},
    )
    graph.add_edge("anomaly_detector_stub", END)
    graph.add_edge("evidence_composer_stub", END)
    graph.add_edge("incident_escalator_stub", END)

    return graph.compile()
