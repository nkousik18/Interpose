"""Report Composer node (docs/INTERPOSE_SCOPING.md Section 9.7): the second and final
LLM node -- writes the investigation's narrative conclusion from the Assessment and
Recommendation. Same reuse-not-reinvent choice and fallback discipline as
assessment.py."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from aml_investigator.state import InvestigationReport, InvestigationState
from interpose.control_plane.llm import LLMError, generate_structured

NodeFn = Callable[[InvestigationState], Awaitable[dict]]


def _fallback_report(state: InvestigationState) -> InvestigationReport:
    assert state.assessment is not None
    assert state.recommendation is not None
    return InvestigationReport(
        summary=(
            f"Account {state.alert.account_id}: {state.assessment.risk_level} risk, "
            f"recommended disposition {state.recommendation.disposition!r}."
        ),
        narrative=(
            "Narrative generation failed; falling back to a structured summary. "
            f"Findings: {'; '.join(state.assessment.key_findings)}. "
            f"Assessment rationale: {state.assessment.rationale}"
        ),
        recommended_next_steps=["Manual review recommended (automated narrative unavailable)."],
    )


async def _run_report(
    state: InvestigationState, generate_fn: Callable[..., Awaitable[BaseModel]]
) -> InvestigationReport:
    assert state.assessment is not None
    assert state.recommendation is not None
    try:
        return await generate_fn(
            system_prompt=(
                "You are an AML analyst writing the final section of an investigation "
                "report. Write a one-sentence summary, a narrative (3-6 sentences) "
                "covering what was investigated and why, and a short list of "
                "recommended next steps for a compliance reviewer."
            ),
            user_prompt=(
                f"Alert: {state.alert.model_dump()}\n"
                f"Assessment: {state.assessment.model_dump()}\n"
                f"Recommended disposition: {state.recommendation.disposition}\n"
                f"Disposition rationale: {state.recommendation.rationale}\n"
                f"Write outcome: "
                f"{state.recommendation.write_result or state.recommendation.write_error}"
            ),
            output_model=InvestigationReport,
        )
    except LLMError:
        return _fallback_report(state)


def make_report_node(
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> NodeFn:
    async def node(state: InvestigationState) -> dict:
        return {"report": await _run_report(state, generate_fn)}

    return node
