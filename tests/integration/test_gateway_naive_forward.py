"""Phase 1, Day 1 acceptance test (docs/ROADMAP.md): a real MCP client, talking to the
real gateway over streamable-HTTP, gets a request forwarded to a real trivial upstream
MCP server and the response returned, and an unrouted server name 404s. As of Day 3
the gateway also evaluates policy (see test_gateway_policy.py) -- these tests only
exercise `echo`, which has no policy configured against it, so its behavior here is
unchanged from Day 1.

Both the gateway and the upstream server run as real subprocesses listening on real
ports, rather than in-process ASGI test clients, because the streamable-HTTP transport
opens a long-lived GET connection for server-initiated messages -- exercising that
requires an actual live server, not a mocked transport.
"""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

GATEWAY_URL = "http://127.0.0.1:8000/mcp/hello-echo"


async def test_naive_forward_round_trip(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            assert "echo" in [t.name for t in tools.tools]

            result = await session.call_tool("echo", {"text": "hello through interpose"})
            assert result.content[0].text == "hello through interpose"


async def test_unknown_server_returns_404(upstream_and_gateway: None) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://127.0.0.1:8000/mcp/does-not-exist",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_server"
