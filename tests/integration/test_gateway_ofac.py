"""Phase 3, Day 11 acceptance test (docs/ROADMAP.md): the real OFAC sanctions MCP
server (mcp-servers/ofac-sanctions/), proxied through the live gateway exactly like
any other upstream -- no policy pack wired up yet (that's Day 14), just proving the
server itself works end-to-end through Interpose. Points at small local fixture CSVs
(see conftest.py's `ofac_upstream_and_gateway`), not the live Treasury API -- see
mcp-servers/ofac-sanctions/README.md for the separate live-fetch smoke test.
"""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

GATEWAY_URL = "http://127.0.0.1:8000/mcp/ofac-sanctions"


async def test_check_entity_finds_a_real_sdn_entry(ofac_upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "check_entity", {"name": "Aerocaribbean Airlines", "entity_type": "entity"}
            )
            match = result.structuredContent["result"]
            assert match["entry_id"] == "36"
            assert match["is_match"] is True
            assert match["programs"] == ["CUBA"]


async def test_check_alias_finds_entry_only_reachable_by_alias(
    ofac_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # "National Bank of Cuba" is an alias (alt.csv); the primary SDN name is
            # "BANCO NACIONAL DE CUBA" -- check_entity's primary-names-only search
            # wouldn't find this, which is the whole reason check_alias exists.
            result = await session.call_tool("check_alias", {"name": "National Bank of Cuba"})
            matches = result.structuredContent["result"]
            assert any(m["entry_id"] == "306" for m in matches)


async def test_get_entity_detail_returns_full_record_with_aliases(
    ofac_upstream_and_gateway: None,
) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("get_entity_detail", {"sdn_entry_id": "306"})
            # No "result" envelope here, unlike check_entity/check_alias above --
            # FastMCP only wraps structuredContent under "result" when the tool's
            # return type is a Union (SanctionsMatch | None); a single concrete
            # BaseModel return (SDNEntry) becomes the structured content directly.
            entry = result.structuredContent
            assert entry["name"] == "BANCO NACIONAL DE CUBA"
            assert entry["aliases"] == ["NATIONAL BANK OF CUBA"]


async def test_check_entity_rejects_invalid_entity_type(ofac_upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "check_entity", {"name": "anyone", "entity_type": "not-a-real-type"}
            )
            assert result.isError is True
