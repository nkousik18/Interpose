"""Recommendation node (docs/INTERPOSE_SCOPING.md Section 9.7): converts the
Assessment's risk level into a disposition and attempts `mark_investigated` -- the
HITL trigger point named in Section 9.7's diagram. No AML policy pack exists yet as of
Day 13 (Day 14 adds `aml-write-hitl-gate.yaml`), so this call is expected to pass
through untouched today. No special-casing is needed for when a HITL gate *does*
exist later: the gateway's blocking-hold model (concepts/21-redis-and-the-hitl-hold.md)
means `mark_investigated` simply takes longer to return once a hold is possible --
this node already handles a denial via `ToolCallError`, which is the only other shape
a gated call can resolve to."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aml_investigator.gateway_client import InvestigationClient, ToolCallError
from aml_investigator.state import InvestigationState, Recommendation

NodeFn = Callable[[InvestigationState], Awaitable[dict]]

_DISPOSITION_BY_RISK = {"high": "escalate", "medium": "monitor", "low": "cleared"}


def make_recommendation_node(client: InvestigationClient) -> NodeFn:
    async def node(state: InvestigationState) -> dict:
        assert state.assessment is not None
        disposition = _DISPOSITION_BY_RISK[state.assessment.risk_level]
        rationale = state.assessment.rationale

        write_result: dict | None = None
        write_error: str | None = None
        try:
            write_result = await client.mark_investigated(
                state.alert.account_id, disposition, rationale
            )
        except ToolCallError as exc:
            write_error = str(exc)

        return {
            "recommendation": Recommendation(
                disposition=disposition,
                rationale=rationale,
                write_result=write_result,
                write_error=write_error,
            )
        }

    return node
