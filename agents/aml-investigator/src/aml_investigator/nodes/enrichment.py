"""Enrichment node (docs/INTERPOSE_SCOPING.md Section 9.7): builds on Discovery's
findings -- the induced subgraph over the account and its neighbors, the structuring
heuristic, and (only if Discovery's sanctions check actually cleared the match
threshold) the full SDN record for that candidate. Pure tool-calling, no LLM.

`check_entity` always returns its single best candidate against the requested entity
type, whether or not it's a good one (see mcp-servers/ofac-sanctions/src/server.py's
docstring) -- `is_match` is what says whether the score actually cleared the
threshold. Fetching `get_entity_detail` for every low-confidence candidate would mean
this node fires on essentially every account (there's almost always *some* nearest
name in a list of 19k+ entries), which defeats the point of gating it at all."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aml_investigator.gateway_client import InvestigationClient
from aml_investigator.state import EnrichmentFindings, InvestigationState

# Caps how many first-hop neighbors join the induced subgraph query -- a real account
# can have far more counterparties than are useful to render in one subgraph; this
# mirrors the transaction-graph server's own `subgraph`/`max_edges` capping philosophy
# (concepts/29) rather than introducing a second, uncapped fan-out.
MAX_SUBGRAPH_NEIGHBORS = 25

NodeFn = Callable[[InvestigationState], Awaitable[dict]]


def make_enrichment_node(client: InvestigationClient) -> NodeFn:
    async def node(state: InvestigationState) -> dict:
        assert state.discovery is not None  # graph always runs discovery first
        account_id = state.alert.account_id
        neighbor_ids = [n["account_id"] for n in state.discovery.first_hop_neighbors]
        subgraph_accounts = [account_id, *neighbor_ids[:MAX_SUBGRAPH_NEIGHBORS]]

        subgraph = await client.subgraph(subgraph_accounts)
        structuring_signal = await client.structuring_check(account_id)

        sanctions_entity_detail = None
        hit = state.discovery.sanctions_hit
        if hit is not None and hit.get("is_match"):
            sanctions_entity_detail = await client.get_entity_detail(hit["entry_id"])

        return {
            "enrichment": EnrichmentFindings(
                subgraph=subgraph,
                structuring_signal=structuring_signal,
                sanctions_entity_detail=sanctions_entity_detail,
            )
        }

    return node
