"""Builds the investigation graph (docs/INTERPOSE_SCOPING.md Section 9.7): a linear,
5-node flow -- Discovery -> Enrichment -> Assessment -> Recommendation -> Report ->
END. Deliberately linear, not a supervisor-routed graph like the control plane's own
(interpose.control_plane.graph) -- this is a single deterministic investigation
procedure, not a system that needs to route between different kinds of events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from aml_investigator.gateway_client import InvestigationClient
from aml_investigator.nodes.assessment import make_assessment_node
from aml_investigator.nodes.discovery import make_discovery_node
from aml_investigator.nodes.enrichment import make_enrichment_node
from aml_investigator.nodes.recommendation import make_recommendation_node
from aml_investigator.nodes.report import make_report_node
from aml_investigator.state import InvestigationState
from interpose.control_plane.llm import generate_structured


def build_graph(
    client: InvestigationClient,
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> CompiledStateGraph:
    """`generate_fn` defaults to the real Groq-backed `generate_structured` but is
    injectable for tests -- the same seam every control-plane LLM node already
    exposes (interpose.control_plane.graph.build_graph)."""
    graph: StateGraph = StateGraph(InvestigationState)

    graph.add_node("discovery", make_discovery_node(client))
    graph.add_node("enrichment", make_enrichment_node(client))
    graph.add_node("assessment", make_assessment_node(generate_fn))
    graph.add_node("recommendation", make_recommendation_node(client))
    graph.add_node("report", make_report_node(generate_fn))

    graph.set_entry_point("discovery")
    graph.add_edge("discovery", "enrichment")
    graph.add_edge("enrichment", "assessment")
    graph.add_edge("assessment", "recommendation")
    graph.add_edge("recommendation", "report")
    graph.add_edge("report", END)

    return graph.compile()
