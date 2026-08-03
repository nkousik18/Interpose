"""Thin MCP client wrapper that talks to the transaction-graph and ofac-sanctions
servers *through the gateway*, never directly -- the design constraint Section 9.7
states explicitly: "the agent uses Interpose-proxied MCP tools exclusively." Two
separate `ClientSession`s are needed because the two upstream servers are two
separate gateway routes (`/mcp/transaction-graph`, `/mcp/ofac-sanctions`), each its
own MCP session per concepts/09's handshake model -- there's no single session that
spans both. Confirmed live (Phase 3 Day 14): two connections to two different
upstream servers behind the same gateway come back with two completely different
`Mcp-Session-Id` values, since each upstream independently assigns its own during its
own `initialize` handshake.

That matters for policy purposes: `aml-sanctions-required` (Day 14's AML pack) needs
to recognize "this investigation already ran a sanctions check" across both servers,
which `session_id` can't do. Every connection this client opens carries the same
`Authorization: Bearer investigation-<run id>` header instead -- not real
authentication (nothing validates it), just a stable identity the gateway's
`agent_id` extraction already supports, kept consistent across both routes for
exactly this one investigation run.

Every call is recorded to `call_log` regardless of outcome, which is what today's
integration test uses to confirm the ~40-call, multi-tool investigation actually
happened (Section 9.7: "~40-60 tool calls per demo run"), and is exactly the kind of
bookkeeping a real driving agent would want for its own trace anyway.
"""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack
from datetime import date
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from pydantic import BaseModel

TRANSACTION_GRAPH_ROUTE = "transaction-graph"
OFAC_ROUTE = "ofac-sanctions"


class ToolCallRecord(BaseModel):
    server: str
    tool: str
    ok: bool
    error: str | None = None


class ToolCallError(Exception):
    """Raised when a gateway-proxied tool call comes back as an MCP error (a policy
    DENY, a malformed request, an upstream failure -- the client doesn't need to
    distinguish which; the node calling it decides what that means)."""


class InvestigationClient:
    """Async context manager owning both upstream sessions. Construct via
    `InvestigationClient(gateway_base_url).connect()` (an `AsyncExitStack`-backed
    `__aenter__`/`__aexit__` pair), same shape as the `async with ... as (read, write,
    _)` pattern every gateway integration test already uses, just wrapped once so
    each node doesn't repeat it."""

    def __init__(self, gateway_base_url: str = "http://127.0.0.1:8000") -> None:
        self._base_url = gateway_base_url.rstrip("/")
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self.call_log: list[ToolCallRecord] = []
        self.agent_id = f"investigation-{uuid.uuid4()}"

    async def __aenter__(self) -> InvestigationClient:
        self._stack = AsyncExitStack()
        # One shared httpx client, not one per route -- so the same `Authorization`
        # header (and thus the same gateway-side `agent_id`) is sent on every
        # connection this investigation run opens, on both servers.
        http_client = await self._stack.enter_async_context(
            httpx.AsyncClient(headers={"Authorization": f"Bearer {self.agent_id}"})
        )
        for route in (TRANSACTION_GRAPH_ROUTE, OFAC_ROUTE):
            read, write, _get_session_id = await self._stack.enter_async_context(
                streamable_http_client(f"{self._base_url}/mcp/{route}", http_client=http_client)
            )
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[route] = session
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        assert self._stack is not None
        await self._stack.aclose()

    async def _call(
        self, route: str, tool: str, arguments: dict[str, Any], *, unwrap_envelope: bool
    ) -> Any:
        """`unwrap_envelope` mirrors the FastMCP quirk documented in
        concepts/28-fuzzy-matching-and-sanctions-screening.md: `structuredContent` is
        wrapped under `{"result": ...}` whenever a tool's return type isn't a single
        concrete `BaseModel` (i.e. it returns a list, or a `Model | None` union) --
        both cases this client needs to unwrap the same way.

        Two distinct error shapes exist and both must become `ToolCallError`: a tool
        *implementation* error (e.g. a bad `disposition` value) comes back as a
        successful JSON-RPC response with `isError=True`; a gateway *policy* denial
        (DENY, a malformed request) is a JSON-RPC-envelope-level error, which the MCP
        SDK raises as `McpError` from `call_tool` itself rather than returning.
        Missing the second case was a real bug this client shipped with (Day 13, no
        AML pack existed yet to ever produce a DENY) -- caught the moment
        Day 14's pack made a real denial reachable for the first time.
        """
        session = self._sessions[route]
        try:
            result = await session.call_tool(tool, arguments)
        except McpError as exc:
            # The actual "why" (e.g. which policy fired, and its reason) lives in
            # `error.data`, not `error.message` -- the gateway's `_error_response`
            # always uses a fixed, generic `message` like "policy_denied" and puts
            # the specifics in `data` (interpose.gateway.app._policy_denied_response).
            message = f"{exc.error.message}: {exc.error.data}"
            self.call_log.append(ToolCallRecord(server=route, tool=tool, ok=False, error=message))
            raise ToolCallError(f"{route}.{tool}({arguments}) failed: {message}") from exc
        if result.isError:
            message = result.content[0].text if result.content else "unknown error"
            self.call_log.append(ToolCallRecord(server=route, tool=tool, ok=False, error=message))
            raise ToolCallError(f"{route}.{tool}({arguments}) failed: {message}")
        self.call_log.append(ToolCallRecord(server=route, tool=tool, ok=True))
        content = result.structuredContent
        return content["result"] if unwrap_envelope else content

    # -- transaction-graph tools -------------------------------------------------

    async def query_transactions(
        self, account_id: str, from_date: date, to_date: date
    ) -> list[dict]:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "query_transactions",
            {
                "account_id": account_id,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
            unwrap_envelope=True,
        )

    async def get_account(self, account_id: str) -> dict:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "get_account",
            {"account_id": account_id},
            unwrap_envelope=False,
        )

    async def neighbors(self, account_id: str, hops: int = 1, min_amount: float = 0) -> list[dict]:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "neighbors",
            {"account_id": account_id, "hops": hops, "min_amount": min_amount},
            unwrap_envelope=True,
        )

    async def subgraph(self, account_ids: list[str], max_edges: int = 500) -> dict:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "subgraph",
            {"account_ids": account_ids, "max_edges": max_edges},
            unwrap_envelope=False,
        )

    async def structuring_check(self, account_id: str, window_days: int = 30) -> dict:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "structuring_check",
            {"account_id": account_id, "window_days": window_days},
            unwrap_envelope=False,
        )

    async def mark_investigated(self, account_id: str, disposition: str, rationale: str) -> dict:
        return await self._call(
            TRANSACTION_GRAPH_ROUTE,
            "mark_investigated",
            {"account_id": account_id, "disposition": disposition, "rationale": rationale},
            unwrap_envelope=False,
        )

    # -- ofac-sanctions tools ------------------------------------------------------

    async def check_entity(self, name: str, entity_type: str = "individual") -> dict | None:
        # SanctionsMatch | None is a Union return type -- wrapped under "result"
        # (concepts/28), unlike get_account/subgraph/etc.'s concrete single models.
        return await self._call(
            OFAC_ROUTE,
            "check_entity",
            {"name": name, "entity_type": entity_type},
            unwrap_envelope=True,
        )

    async def check_alias(self, name: str) -> list[dict]:
        return await self._call(
            OFAC_ROUTE, "check_alias", {"name": name}, unwrap_envelope=True
        )

    async def get_entity_detail(self, sdn_entry_id: str) -> dict:
        return await self._call(
            OFAC_ROUTE,
            "get_entity_detail",
            {"sdn_entry_id": sdn_entry_id},
            unwrap_envelope=False,
        )
