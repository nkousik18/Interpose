"""Phase 2 Day 6 acceptance test (docs/ROADMAP.md): "decisions flow from gateway to
control plane" -- a real call through the live gateway, and proof the background
control plane actually picked it up and ran Agent A1, by polling the one real,
externally-observable side effect A1 produces: the `interpose:session:{session_id}`
risk-score hash (Section 6.8) written by
interpose.control_plane.agents.policy_evaluator._record_session_risk_score.
"""

import asyncio
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from interpose.config import get_settings
from interpose.session.redis_client import create_async_redis

GATEWAY_URL = "http://127.0.0.1:8000/mcp/hello-echo"


async def _wait_for_session_risk_score(session_id: str, timeout: float = 5.0) -> dict[str, str]:
    conn = create_async_redis(get_settings().redis_url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = await conn.hgetall(f"interpose:session:{session_id}")
            if data:
                return data
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"control plane never wrote a session-risk-score hash for {session_id!r}"
        )
    finally:
        await conn.aclose()


async def test_a_pass_call_through_the_gateway_reaches_the_control_plane(
    upstream_and_gateway: None,
) -> None:
    captured_session_id = None

    async with streamable_http_client(GATEWAY_URL) as (read, write, get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            captured_session_id = get_session_id()
            await session.call_tool("echo", {"text": "reach the control plane"})

    assert captured_session_id is not None
    data = await _wait_for_session_risk_score(captured_session_id)
    assert data["agent_id"] == "anonymous"
    assert 0.0 <= float(data["risk_score"]) <= 1.0
