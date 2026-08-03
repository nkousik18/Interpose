"""Discovery node (docs/INTERPOSE_SCOPING.md Section 9.7): the investigation's first
step -- pull up the flagged account, a sanctions check on the account holder, its
transaction history, and its immediate counterparties. No LLM involved; this node is
pure tool-calling, same as Enrichment.

Call order matters as of Phase 3 Day 14's AML policy pack: `get_account` must run
first (it's the only way to learn the entity's name at all, and is deliberately left
ungated -- see policies/packs/aml/aml-sanctions-required.yaml), then `check_entity`
right after, before any other transaction-graph call -- `aml-sanctions-required`
denies `query_transactions`/`neighbors` otherwise. This ordering isn't a workaround;
it's what a real AML policy pack is supposed to do: shape investigation procedure,
not just rubber-stamp whatever order an agent happens to call things in.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date

from aml_investigator.gateway_client import InvestigationClient
from aml_investigator.state import DiscoveryFindings, InvestigationState

# A wide, fixed window rather than "today" -- this is 2022 synthetic data, not live
# traffic, same reasoning as structuring_check's own window-anchoring
# (concepts/29-embedded-analytics-with-duckdb.md).
QUERY_FROM_DATE = date(2000, 1, 1)
QUERY_TO_DATE = date(2035, 12, 31)

NodeFn = Callable[[InvestigationState], Awaitable[dict]]


def make_discovery_node(client: InvestigationClient) -> NodeFn:
    async def node(state: InvestigationState) -> dict:
        account_id = state.alert.account_id
        account = await client.get_account(account_id)
        # entity_type="entity" -- the accounts in this dataset are corporate/shell
        # entities, not natural persons (see graph_models.AccountRecord.entity_name).
        # Must run before any other transaction-graph call below -- see module
        # docstring.
        sanctions_hit = await client.check_entity(account["entity_name"], entity_type="entity")
        transactions = await client.query_transactions(account_id, QUERY_FROM_DATE, QUERY_TO_DATE)
        first_hop_neighbors = await client.neighbors(account_id, hops=1)

        return {
            "discovery": DiscoveryFindings(
                account=account,
                transactions=transactions,
                sanctions_hit=sanctions_hit,
                first_hop_neighbors=first_hop_neighbors,
            )
        }

    return node
