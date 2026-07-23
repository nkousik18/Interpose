"""Phase 1, Day 5 acceptance tests (docs/ROADMAP.md): the two end-to-end paths not
already covered elsewhere -- malformed request (test_gateway_naive_forward.py has
happy path + unknown server; test_gateway_policy.py has the deny path) and rate limit,
completing the "5+ end-to-end tests" checklist from scoping doc Section 14.5 Day 5.
"""

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

GATEWAY_URL = "http://127.0.0.1:8000/mcp/hello-echo"


async def test_malformed_request_returns_400(upstream_and_gateway: None) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://127.0.0.1:8000/mcp/hello-echo",
            content=b"{not valid json-rpc at all",
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 400
    assert response.json()["error"] == "malformed_mcp_envelope"


async def test_rate_limited_tool_denies_the_second_call(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            first = await session.call_tool("throttled_tool", {})
            assert first.content[0].text == "called"

            with pytest.raises(McpError) as exc_info:
                await session.call_tool("throttled_tool", {})
            assert exc_info.value.error.data["reason"] == "rate_limit_exceeded"
            assert exc_info.value.error.data["policy"] == "hello-echo-throttle-test-tool"
