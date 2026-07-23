"""The Interpose gateway: Stages 1-9 of the request lifecycle
(docs/INTERPOSE_SCOPING.md Section 6.5).

Request bodies are single JSON-RPC envelopes (buffered and parsed whole -- that's how
MCP's streamable-http transport uses POST). Responses are streamed chunk-by-chunk
rather than buffered, because the transport also uses a long-lived GET request for
server-initiated messages: buffering that response would mean waiting for a stream
that's never supposed to end.

Policy (Stages 4-5) and audit (Stages 6 and 8) only apply to `tools/call` requests --
the actual governed action. Session-management traffic (`initialize`, `list_tools`,
`notifications/*`, the long-lived GET stream) bypasses both entirely and forwards
exactly as it did on Day 1: there's no `{server, tool}` pair for a policy to match
against, and no single well-defined "completion" moment to audit for a stream that's
designed to stay open.

A `tools/call` request produces either one audit row (DENIED -- nothing is pending,
so there's no intent to record separately) or two linked rows (PASS: an INTENT row
written *before* forwarding, so the audit log shows intent even if the forward step
itself crashes; then a COMPLETED or UPSTREAM_ERROR row after, linked via `parent_id`).
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from mcp.types import ErrorData, JSONRPCError, JSONRPCMessage
from pydantic import ValidationError

from interpose.audit.chain import canonical_json
from interpose.audit.db import create_engine, create_session_factory
from interpose.audit.store import AuditStore
from interpose.config import get_settings
from interpose.gateway.routing import DEFAULT_CONFIG_PATH, RoutingTable, load_routing_table
from interpose.policies.loader import load_policy_pack
from interpose.policies.policyset import Outcome, PolicyDecision, PolicyEngine, RateLimiter

logger = logging.getLogger(__name__)

DEFAULT_POLICY_DIR = Path("config/policies")

# JSON-RPC reserves -32000 to -32099 for implementation-defined server errors.
POLICY_DENIED_ERROR_CODE = -32001
UPSTREAM_ERROR_CODE = -32002

# Headers meaningful to the MCP streamable-http transport (plus Authorization, read
# now for future policy/audit use even though nothing enforces it yet) -- forwarded to
# the upstream as-is. Everything else (Host, Content-Length, ...) is specific to the
# client-to-gateway hop and shouldn't be replayed onto the gateway-to-upstream hop.
FORWARD_REQUEST_HEADERS = {
    "content-type",
    "accept",
    "mcp-session-id",
    "mcp-protocol-version",
    "last-event-id",
    "authorization",
}
# Hop-by-hop / transport-specific response headers that don't survive re-proxying.
STRIP_RESPONSE_HEADERS = {"content-length", "connection", "transfer-encoding", "content-encoding"}


def create_app(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    policy_dir: Path | str = DEFAULT_POLICY_DIR,
    database_url: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.routing = load_routing_table(config_path)
        app.state.policy_engine = PolicyEngine(load_policy_pack(policy_dir))
        app.state.rate_limiter = RateLimiter()
        app.state.http_client = httpx.AsyncClient()
        engine = create_engine(database_url or get_settings().database_url)
        app.state.audit_store = AuditStore(create_session_factory(engine))
        logger.info("gateway.started routes=%s", list(app.state.routing.servers.keys()))
        try:
            yield
        finally:
            await app.state.http_client.aclose()
            await engine.dispose()

    app = FastAPI(title="Interpose gateway", lifespan=lifespan)

    @app.api_route("/mcp/{server_name}", methods=["GET", "POST", "DELETE"])
    async def proxy_mcp(server_name: str, request: Request) -> Response:
        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("x-correlation-id", request_id)
        agent_id = _extract_agent_id(request)
        logger.info(
            "gateway.ingress request_id=%s correlation_id=%s agent_id=%s server=%s method=%s",
            request_id,
            correlation_id,
            agent_id,
            server_name,
            request.method,
        )

        body = await request.body()
        message: JSONRPCMessage | None = None
        if body:
            try:
                message = JSONRPCMessage.model_validate_json(body)
                logger.info(
                    "gateway.parsed request_id=%s rpc_method=%s",
                    request_id,
                    getattr(message.root, "method", None),
                )
            except ValidationError as exc:
                logger.warning("gateway.malformed request_id=%s error=%s", request_id, exc)
                return JSONResponse(
                    status_code=400,
                    content={"error": "malformed_mcp_envelope", "detail": str(exc)},
                )

        routing: RoutingTable = request.app.state.routing
        upstream = routing.resolve(server_name)
        if upstream is None:
            # No audit entry for this either -- there's no {server, tool} pair to
            # attach one to, same reasoning as the tools/call-only scoping below.
            logger.warning(
                "gateway.unknown_server request_id=%s server=%s", request_id, server_name
            )
            return JSONResponse(
                status_code=404, content={"error": "unknown_server", "server": server_name}
            )

        client: httpx.AsyncClient = request.app.state.http_client
        forward_headers = {
            k: v for k, v in request.headers.items() if k.lower() in FORWARD_REQUEST_HEADERS
        }

        tool_call = _extract_tool_call(message)
        if tool_call is None:
            return await _forward(
                client, request.method, upstream.url, forward_headers, body, request_id
            )

        return await _handle_tool_call(
            request=request,
            server_name=server_name,
            upstream_url=upstream.url,
            tool_name=tool_call.tool_name,
            arguments=tool_call.arguments,
            rpc_id=tool_call.rpc_id,
            agent_id=agent_id,
            session_id=request.headers.get("mcp-session-id", "unknown"),
            forward_headers=forward_headers,
            body=body,
            request_id=request_id,
        )

    return app


def _extract_agent_id(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return None


class ToolCall:
    def __init__(self, tool_name: str, arguments: dict[str, Any], rpc_id: str | int) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.rpc_id = rpc_id


def _extract_tool_call(message: JSONRPCMessage | None) -> ToolCall | None:
    """If `message` is a `tools/call` request, pull out what policy/audit need."""
    if message is None:
        return None
    root = message.root
    if getattr(root, "method", None) != "tools/call":
        return None
    params = getattr(root, "params", None) or {}
    tool_name = params.get("name")
    if not tool_name:
        return None
    return ToolCall(tool_name, params.get("arguments") or {}, root.id)


async def _handle_tool_call(
    *,
    request: Request,
    server_name: str,
    upstream_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    rpc_id: str | int,
    agent_id: str | None,
    session_id: str,
    forward_headers: dict[str, str],
    body: bytes,
    request_id: str,
) -> Response:
    policy_engine: PolicyEngine = request.app.state.policy_engine
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    audit_store: AuditStore = request.app.state.audit_store
    client: httpx.AsyncClient = request.app.state.http_client

    decision, policies_fired = _compile_and_evaluate(
        policy_engine, rate_limiter, server_name, tool_name, agent_id, request_id
    )
    trace_id = uuid.uuid4()
    args_hash = hashlib.sha256(canonical_json(arguments).encode("utf-8")).hexdigest()
    subject = agent_id or "anonymous"

    if decision.outcome is Outcome.DENY:
        logger.warning(
            "gateway.policy_denied request_id=%s server=%s tool=%s fired_policy=%s reason=%s",
            request_id,
            server_name,
            tool_name,
            decision.fired_policy,
            decision.reason,
        )
        await audit_store.write_entry(
            status="DENIED",
            trace_id=trace_id,
            span_id=uuid.uuid4(),
            agent_id=subject,
            session_id=session_id,
            server=server_name,
            tool=tool_name,
            args_hash=args_hash,
            args_redacted=arguments,  # no PII redaction implemented yet (Day 3 stub)
            policies_fired=policies_fired,
            decision=_decision_payload(decision),
        )
        return _policy_denied_response(rpc_id, decision)

    logger.info(
        "gateway.policy_passed request_id=%s server=%s tool=%s fired_policy=%s",
        request_id,
        server_name,
        tool_name,
        decision.fired_policy,
    )
    intent = await audit_store.write_entry(
        status="INTENT",
        trace_id=trace_id,
        span_id=uuid.uuid4(),
        agent_id=subject,
        session_id=session_id,
        server=server_name,
        tool=tool_name,
        args_hash=args_hash,
        args_redacted=arguments,
        policies_fired=policies_fired,
        decision=_decision_payload(decision),
    )

    start = time.monotonic()
    try:
        response = await _forward(
            client, request.method, upstream_url, forward_headers, body, request_id
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("gateway.upstream_error request_id=%s", request_id)
        await audit_store.write_entry(
            status="UPSTREAM_ERROR",
            trace_id=trace_id,
            span_id=uuid.uuid4(),
            parent_id=intent.id,
            agent_id=subject,
            session_id=session_id,
            server=server_name,
            tool=tool_name,
            args_hash=args_hash,
            args_redacted=arguments,
            policies_fired=policies_fired,
            decision={"outcome": "UPSTREAM_ERROR", "detail": str(exc)},
            latency_ms=latency_ms,
        )
        return _upstream_error_response(rpc_id, exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    # Latency measures time-to-response-headers, not full body consumption -- the
    # response streams from here (see _forward), and a tool call's body is normally
    # a single message anyway, so this is a reasonable proxy without re-buffering.
    await audit_store.write_entry(
        status="COMPLETED",
        trace_id=trace_id,
        span_id=uuid.uuid4(),
        parent_id=intent.id,
        agent_id=subject,
        session_id=session_id,
        server=server_name,
        tool=tool_name,
        args_hash=args_hash,
        args_redacted=arguments,
        policies_fired=policies_fired,
        decision=_decision_payload(decision),
        latency_ms=latency_ms,
    )
    return response


def _decision_payload(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "outcome": decision.outcome.value,
        "fired_policy": decision.fired_policy,
        "reason": decision.reason,
    }


def _compile_and_evaluate(
    policy_engine: PolicyEngine,
    rate_limiter: RateLimiter,
    server_name: str,
    tool_name: str,
    agent_id: str | None,
    request_id: str,
) -> tuple[PolicyDecision, list[dict[str, str]]]:
    try:
        policy_set = policy_engine.compile(server_name, tool_name)
        decision = policy_set.evaluate(rate_limiter, subject=agent_id or "anonymous")
        policies_fired = [
            {"policy": p.policy, "effect_type": p.effect.type} for p in policy_set.policies
        ]
        return decision, policies_fired
    except Exception:
        # Fail-closed per Section 6.5: a policy engine error must never silently
        # become a pass-through.
        logger.exception("gateway.policy_engine_error request_id=%s", request_id)
        return PolicyDecision(Outcome.DENY, None, "policy_engine_error"), []


def _policy_denied_response(rpc_id: str | int, decision: PolicyDecision) -> Response:
    error = JSONRPCError(
        jsonrpc="2.0",
        id=rpc_id,
        error=ErrorData(
            code=POLICY_DENIED_ERROR_CODE,
            message="policy_denied",
            data={"policy": decision.fired_policy, "reason": decision.reason},
        ),
    )
    body = JSONRPCMessage(error).model_dump_json()
    return Response(content=body, media_type="application/json")


def _upstream_error_response(rpc_id: str | int, exc: Exception) -> Response:
    error = JSONRPCError(
        jsonrpc="2.0",
        id=rpc_id,
        error=ErrorData(
            code=UPSTREAM_ERROR_CODE, message="upstream_error", data={"detail": str(exc)}
        ),
    )
    body = JSONRPCMessage(error).model_dump_json()
    return Response(content=body, media_type="application/json")


async def _forward(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    request_id: str,
) -> StreamingResponse:
    req = client.build_request(method, url, headers=headers, content=body or None)
    upstream_response = await client.send(req, stream=True)

    async def body_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_raw():
                yield chunk
        finally:
            await upstream_response.aclose()
            logger.info(
                "gateway.egress request_id=%s status=%d", request_id, upstream_response.status_code
            )

    response_headers = {
        k: v
        for k, v in upstream_response.headers.items()
        if k.lower() not in STRIP_RESPONSE_HEADERS
    }
    return StreamingResponse(
        body_stream(), status_code=upstream_response.status_code, headers=response_headers
    )
