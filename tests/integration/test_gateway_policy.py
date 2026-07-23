"""Phase 1, Day 3 acceptance test (docs/ROADMAP.md): the policy engine actually fires
inside the live gateway. `config/policies/hello-echo-denylist.yaml` denylists
`dangerous_tool` on the `hello-echo` upstream; `echo` has no policy against it and
stays default-allow (Stage 4-5 of docs/INTERPOSE_SCOPING.md Section 6.5).
"""

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

GATEWAY_URL = "http://127.0.0.1:8000/mcp/hello-echo"


async def test_denied_tool_call_returns_structured_error(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            try:
                await session.call_tool("dangerous_tool", {})
            except McpError as exc:
                assert exc.error.message == "policy_denied"
                assert exc.error.data["policy"] == "hello-echo-no-dangerous-tool"
                expected_reason = "dangerous_tool is denylisted for this local demo"
                assert exc.error.data["reason"] == expected_reason
            else:
                raise AssertionError("expected the denylisted tool call to raise McpError")


async def test_allowed_tool_call_still_passes(upstream_and_gateway: None) -> None:
    async with streamable_http_client(GATEWAY_URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("echo", {"text": "policy engine says pass"})
            assert result.content[0].text == "policy engine says pass"
