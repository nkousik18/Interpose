"""Builds the LangGraph control-plane graph (docs/INTERPOSE_SCOPING.md Section 7.5).

All five agents are real as of Phase 2 Day 8. `incident_escalator` is reachable via
two paths: directly from the Supervisor on `DENY`, and from `anomaly_detector` when it
raises a high-severity flag (the third routing hop added this day -- see
`interpose.control_plane.agents.supervisor`'s module docstring for the one promotion
path that still isn't wired up).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.control_plane.agents.anomaly_detector import make_anomaly_detector_node
from interpose.control_plane.agents.evidence_composer import make_evidence_composer_node
from interpose.control_plane.agents.incident_escalator import make_incident_escalator_node
from interpose.control_plane.agents.policy_evaluator import make_policy_evaluator_node
from interpose.control_plane.agents.supervisor import (
    route_after_anomaly_detector,
    route_after_policy_evaluator,
    route_after_supervisor,
)
from interpose.control_plane.llm import generate_structured
from interpose.control_plane.state import InterposeState


async def _supervisor_node(state: InterposeState) -> dict:
    """A0 itself does no work on state -- Section 7.6: pure dispatch. Routing
    happens via the conditional-edge functions LangGraph calls separately; this node
    only exists to give the graph an explicit, nameable entry point to route from."""
    return {}


def build_graph(
    session_factory: async_sessionmaker,
    redis_conn: Redis,
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> CompiledStateGraph:
    """`generate_fn` defaults to the real Groq-backed `generate_structured`, but
    tests can inject a fake (no network, deterministic) -- the same seam each
    LLM-calling agent's own node factory already exposes individually."""
    graph: StateGraph = StateGraph(InterposeState)

    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("policy_evaluator", make_policy_evaluator_node(session_factory, redis_conn))
    graph.add_node(
        "anomaly_detector", make_anomaly_detector_node(session_factory, generate_fn)
    )
    graph.add_node(
        "evidence_composer", make_evidence_composer_node(session_factory, generate_fn)
    )
    graph.add_node(
        "incident_escalator", make_incident_escalator_node(session_factory, generate_fn)
    )

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"to_a1": "policy_evaluator", "to_a4": "incident_escalator"},
    )
    graph.add_conditional_edges(
        "policy_evaluator",
        route_after_policy_evaluator,
        {"to_a2": "anomaly_detector", "to_a3": "evidence_composer", "end": END},
    )
    graph.add_conditional_edges(
        "anomaly_detector",
        route_after_anomaly_detector,
        {"to_a4": "incident_escalator", "end": END},
    )
    graph.add_edge("evidence_composer", END)
    graph.add_edge("incident_escalator", END)

    return graph.compile()
