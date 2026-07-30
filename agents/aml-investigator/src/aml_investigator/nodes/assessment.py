"""Assessment node (docs/INTERPOSE_SCOPING.md Section 9.7): the first of two LLM
nodes -- reasons over Discovery + Enrichment's evidence to produce a risk level,
findings, and rationale. Reuses `interpose.control_plane.llm.generate_structured`
(Groq, strict JSON schema) rather than a second hand-rolled wrapper; `generate_fn` is
still injectable, same seam every control-plane LLM node already exposes, so tests
never need a real API key (tests/conftest.py forces `GROQ_API_KEY=""` for exactly this
reason).

On `LLMError`, falls back to a deterministic heuristic rather than failing the whole
investigation -- same "produce something a reviewer can act on" discipline as the
control plane's `evidence_composer` fallback.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from aml_investigator.state import Assessment, InvestigationState
from interpose.control_plane.llm import LLMError, generate_structured

NodeFn = Callable[[InvestigationState], Awaitable[dict]]


def _fallback_assessment(state: InvestigationState) -> Assessment:
    assert state.discovery is not None
    assert state.enrichment is not None
    findings: list[str] = []
    risk = "low"

    sanctions_hit = state.discovery.sanctions_hit
    if sanctions_hit is not None and sanctions_hit.get("is_match"):
        findings.append(
            f"Sanctions match: {sanctions_hit['matched_name']!r} "
            f"(score {sanctions_hit['score']:.0f})"
        )
        risk = "high"

    signal = state.enrichment.structuring_signal
    if signal.get("flagged"):
        findings.append(
            f"Structuring signature: {signal['deposit_count']} sub-threshold deposits "
            f"totaling {signal['total_deposits']:.2f} within {signal['window_days']} days"
        )
        risk = "high" if risk == "high" else "medium"

    if not findings:
        findings.append("No sanctions match or structuring signal found in available evidence")

    return Assessment(
        risk_level=risk,
        key_findings=findings,
        rationale="Deterministic fallback assessment (LLM reasoning unavailable).",
    )


async def _run_assessment(
    state: InvestigationState, generate_fn: Callable[..., Awaitable[BaseModel]]
) -> Assessment:
    assert state.discovery is not None
    assert state.enrichment is not None
    try:
        return await generate_fn(
            system_prompt=(
                "You are an AML (anti-money-laundering) analyst assessing a "
                "suspicious-activity alert. Given the account, transaction, sanctions, "
                "and structuring evidence collected so far, assess the account's risk "
                "level (low/medium/high), list the specific findings that drove the "
                "assessment, and give a short rationale."
            ),
            user_prompt=(
                f"Alert: {state.alert.model_dump()}\n"
                f"Account: {state.discovery.account}\n"
                f"Transaction count: {len(state.discovery.transactions)}\n"
                f"Sanctions check on account holder: {state.discovery.sanctions_hit}\n"
                f"First-hop neighbors: {state.discovery.first_hop_neighbors}\n"
                f"Induced subgraph: {state.enrichment.subgraph}\n"
                f"Structuring signal: {state.enrichment.structuring_signal}\n"
                f"Sanctions entity detail: {state.enrichment.sanctions_entity_detail}"
            ),
            output_model=Assessment,
        )
    except LLMError:
        return _fallback_assessment(state)


def make_assessment_node(
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> NodeFn:
    async def node(state: InvestigationState) -> dict:
        return {"assessment": await _run_assessment(state, generate_fn)}

    return node
