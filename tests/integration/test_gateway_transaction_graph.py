"""Phase 3, Day 12 acceptance test (docs/ROADMAP.md): the real transaction-graph MCP
server (mcp-servers/transaction-graph/), proxied through the live gateway exactly like
any other upstream -- no policy pack wired up yet (that's Day 14), just proving the
server itself works end-to-end through Interpose. Points at the small local fixture
CSVs (see conftest.py's `transaction_graph_upstream_and_gateway`), not the real ~150MB
subsampled dataset.
"""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

GATEWAY_URL = "http://127.0.0.1:8000/mcp/transaction-graph"


async def test_query_transactions_filters_by_date_range(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "query_transactions",
                {"account_id": "1:ACC001", "from_date": "2022-09-01", "to_date": "2022-09-30"},
            )
            txns = result.structuredContent["result"]
            assert len(txns) == 4  # excludes the 2022-08-01 deposit


async def test_get_account_returns_live_summary_stats(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("get_account", {"account_id": "1:ACC001"})
            # No "result" envelope here, unlike list-returning tools above -- a
            # single concrete BaseModel return becomes the structured content
            # directly (same FastMCP quirk documented in concepts/28).
            account = result.structuredContent
            assert account["entity_name"] == "Suspect Corp"
            assert account["total_transactions"] == 5


async def test_neighbors_two_hops_reaches_the_second_hop_account(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("neighbors", {"account_id": "1:ACC001", "hops": 2})
            links = {link["account_id"]: link for link in result.structuredContent["result"]}
            assert links["3:ACC020"]["hop"] == 2


async def test_structuring_check_flags_the_seeded_pattern(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("structuring_check", {"account_id": "1:ACC001"})
            signal = result.structuredContent
            assert signal["flagged"] is True
            assert signal["deposit_count"] == 3


async def test_subgraph_returns_induced_edges(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "subgraph", {"account_ids": ["1:ACC001", "2:ACC010", "3:ACC020"]}
            )
            graph = result.structuredContent
            assert len(graph["edges"]) == 2
            assert graph["truncated"] is False


async def test_mark_investigated_records_a_disposition(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "mark_investigated",
                {
                    "account_id": "1:ACC001",
                    "disposition": "escalate",
                    "rationale": "structuring pattern confirmed via investigation",
                },
            )
            write_result = result.structuredContent
            assert write_result["disposition"] == "escalate"


async def test_mark_investigated_rejects_invalid_disposition(
    transaction_graph_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "mark_investigated",
                {
                    "account_id": "1:ACC001",
                    "disposition": "not-a-real-disposition",
                    "rationale": "x",
                },
            )
            assert result.isError is True
