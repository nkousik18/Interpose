"""Discovery node (docs/INTERPOSE_SCOPING.md Section 9.7): the investigation's first
step -- pull up the flagged account, its transaction history, a sanctions check on the
account holder, and its immediate counterparties. No LLM involved; this node is pure
tool-calling, same as Enrichment."""

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
        transactions = await client.query_transactions(account_id, QUERY_FROM_DATE, QUERY_TO_DATE)
        # entity_type="entity" -- the accounts in this dataset are corporate/shell
        # entities, not natural persons (see graph_models.AccountRecord.entity_name).
        sanctions_hit = await client.check_entity(account["entity_name"], entity_type="entity")
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
