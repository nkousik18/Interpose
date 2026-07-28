"""Transaction-graph MCP server (docs/INTERPOSE_SCOPING.md Section 9.6, Phase 3 Day
12). Exposes the subsampled IBM AML transaction data as a queryable graph over
streamable-HTTP -- same transport as the gateway proxies elsewhere
(concepts/09-mcp-handshake-and-transports.md). Data is loaded as DuckDB views over
Parquet/CSV at startup (see store.py); `mark_investigated` is the one write tool,
landing in an in-memory table that resets on every restart.

Tool functions below are thin wrappers around store.py's pure query functions --
store.py takes a `GraphStore` and plain arguments so its logic is unit-testable
without an MCP server or Context in the loop at all.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import store as graph_store
from graph_models import (
    AccountLink,
    AccountRecord,
    GraphResponse,
    StructuringSignal,
    Transaction,
    WriteResult,
)
from mcp.server.fastmcp import Context, FastMCP
from store import GraphStore

from config import Settings

logger = logging.getLogger(__name__)


def _lifespan_for(settings: Settings):
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[GraphStore]:
        store = graph_store.build_store(
            transactions_source=settings.transactions_source,
            accounts_source=settings.accounts_source,
            small_deposit_threshold=settings.small_deposit_threshold,
            min_structuring_deposits=settings.min_structuring_deposits,
            max_hops=settings.max_hops,
        )
        txn_count, account_count = graph_store.row_counts(store)
        logger.info(
            "transaction_graph.loaded transactions=%d accounts=%d transactions_source=%s "
            "accounts_source=%s",
            txn_count,
            account_count,
            settings.transactions_source,
            settings.accounts_source,
        )
        yield store

    return lifespan


def _store(ctx: Context | None) -> GraphStore:
    return ctx.request_context.lifespan_context


def build_server(settings: Settings) -> FastMCP:
    mcp = FastMCP(
        "transaction-graph",
        host=settings.host,
        port=settings.port,
        lifespan=_lifespan_for(settings),
    )

    @mcp.tool()
    def query_transactions(
        account_id: str, from_date: date, to_date: date, ctx: Context | None = None
    ) -> list[Transaction]:
        """List transactions touching `account_id` (as sender or receiver) with a
        timestamp in `[from_date, to_date]` inclusive."""
        return graph_store.query_transactions(_store(ctx), account_id, from_date, to_date)

    @mcp.tool()
    def get_account(account_id: str, ctx: Context | None = None) -> AccountRecord:
        """Account metadata plus summary statistics (transaction count, totals sent/
        received, distinct counterparties, first/last activity) computed live from
        the transaction data."""
        record = graph_store.get_account(_store(ctx), account_id)
        if record is None:
            raise ValueError(f"no account with account_id={account_id!r}")
        return record

    @mcp.tool()
    def neighbors(
        account_id: str, hops: int = 1, min_amount: float = 0, ctx: Context | None = None
    ) -> list[AccountLink]:
        """k-hop neighborhood of `account_id`'s counterparties (breadth-first, `hops`
        clamped to the server's configured max), aggregating amount/count per
        counterparty and filtering out any single transaction under `min_amount`."""
        return graph_store.neighbors(_store(ctx), account_id, hops, min_amount)

    @mcp.tool()
    def subgraph(
        account_ids: list[str], max_edges: int = 500, ctx: Context | None = None
    ) -> GraphResponse:
        """Induced subgraph over `account_ids`: every aggregated edge whose both
        endpoints are in the set, capped at `max_edges` (highest-amount edges kept;
        `truncated` says whether anything was cut)."""
        return graph_store.subgraph(_store(ctx), account_ids, max_edges)

    @mcp.tool()
    def structuring_check(
        account_id: str, window_days: int = 30, ctx: Context | None = None
    ) -> StructuringSignal:
        """Canned structuring ("smurfing") heuristic: flags `account_id` if it
        received enough sub-threshold deposits, summing past the reporting
        threshold, within the trailing `window_days` of its own activity."""
        return graph_store.structuring_check(_store(ctx), account_id, window_days)

    @mcp.tool()
    def mark_investigated(
        account_id: str, disposition: str, rationale: str, ctx: Context | None = None
    ) -> WriteResult:
        """The write action: records a disposition (`cleared` | `escalate` |
        `monitor`) for `account_id` in an in-memory table that resets on restart --
        exists solely to demonstrate HITL gating and audit on a mutating call."""
        if disposition not in graph_store.VALID_DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of {sorted(graph_store.VALID_DISPOSITIONS)}, "
                f"got {disposition!r}"
            )
        return graph_store.mark_investigated(_store(ctx), account_id, disposition, rationale)

    return mcp


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_server(Settings()).run(transport="streamable-http")
