"""Typed state for the investigation graph (docs/INTERPOSE_SCOPING.md Section 9.7).

One Pydantic model per node's output, aggregated into `InvestigationState` -- same
"structured object, not a chat transcript" discipline the control plane's own
`InterposeState` already follows (interpose.control_plane.state). Each node returns a
partial dict (`{"discovery": DiscoveryFindings(...)}`) that LangGraph merges into the
running state by key, so later nodes only need to declare which earlier slots they
read.

Tool-call bookkeeping (what was called, in what order, whether it succeeded) is
deliberately *not* a state field here -- it lives on the `InvestigationClient` instance
itself (gateway_client.py), shared by closure across every node's factory function.
Threading it through state would mean every node returning the whole accumulated list
just to append one entry; reading it off the client after the graph finishes is simpler
and there's exactly one client per run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Alert(BaseModel):
    """The investigation's starting point -- what a compliance analyst's alert queue
    would hand the agent (Section 9.5's narrative)."""

    account_id: str
    alert_type: str
    narrative_hint: str | None = None


class DiscoveryFindings(BaseModel):
    """Discovery node's output: `query_transactions`, `get_account`, `check_entity`,
    `neighbors` (Section 9.7's node diagram)."""

    account: dict
    transactions: list[dict]
    sanctions_hit: dict | None
    first_hop_neighbors: list[dict]


class EnrichmentFindings(BaseModel):
    """Enrichment node's output: `subgraph`, `structuring_check`,
    `get_entity_detail` (Section 9.7's node diagram)."""

    subgraph: dict
    structuring_signal: dict
    sanctions_entity_detail: dict | None


class Assessment(BaseModel):
    """Assessment node's output -- LLM reasoning over Discovery + Enrichment
    evidence, or a deterministic fallback if the LLM call fails
    (see nodes/assessment.py)."""

    risk_level: Literal["low", "medium", "high"]
    key_findings: list[str]
    rationale: str


class Recommendation(BaseModel):
    """Recommendation node's output: the disposition decision plus the outcome of
    attempting `mark_investigated` -- the HITL trigger point (Section 9.7). No AML
    policy pack exists yet as of Day 13 (that's Day 14), so this call is expected to
    pass through untouched today; the gateway's blocking-hold model (concepts/21)
    means a future HITL gate needs no special-casing here at all -- `mark_investigated`
    simply takes longer to return once one exists."""

    disposition: Literal["cleared", "monitor", "escalate"]
    rationale: str
    write_result: dict | None
    write_error: str | None


class InvestigationReport(BaseModel):
    """Report Composer node's output -- the final narrative, or a deterministic
    fallback if the LLM call fails (see nodes/report.py)."""

    summary: str
    narrative: str
    recommended_next_steps: list[str]


class InvestigationState(BaseModel):
    alert: Alert
    discovery: DiscoveryFindings | None = None
    enrichment: EnrichmentFindings | None = None
    assessment: Assessment | None = None
    recommendation: Recommendation | None = None
    report: InvestigationReport | None = None
