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

A `tools/call` request produces one of:
- One `DENIED` row (policy denylist/rate-limit/allowlist -- nothing was ever pending).
- Two linked rows (`PASS`): an `INTENT` row written *before* forwarding, so the audit
  log shows intent even if the forward step itself crashes; then `COMPLETED` or
  `UPSTREAM_ERROR`, linked via `parent_id`.
- Two linked rows (`HOLD`, Phase 2 Day 6): a `HELD` row written when a HITL ticket
  opens, then -- once a reviewer decides, or the ticket times out -- `COMPLETED` (the
  call proceeds), `UPSTREAM_ERROR`, or `DENIED`, linked via `parent_id`. The gateway
  blocks (asynchronously; other requests are unaffected) waiting for that decision --
  see concepts/21-redis-and-the-hitl-hold.md for why this is a deliberate MVP
  simplification rather than the doc's literal "immediate held response" wording.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from mcp.types import ErrorData, JSONRPCError, JSONRPCMessage
from pydantic import ValidationError
from sqlalchemy import text

from interpose.audit.chain import canonical_json
from interpose.audit.db import create_engine, create_session_factory
from interpose.audit.store import AuditStore
from interpose.config import get_settings
from interpose.control_plane.bus import EventBus
from interpose.control_plane.graph import build_graph
from interpose.control_plane.runner import run_forever
from interpose.control_plane.state import Decision as CPDecision
from interpose.control_plane.state import DecisionEvent, PolicyResult
from interpose.gateway.routing import RoutingTable, load_routing_table
from interpose.policies.loader import load_policy_pack
from interpose.policies.policyset import Outcome, PolicyDecision, PolicyEngine, RateLimiter
from interpose.session import hitl
from interpose.session.redis_client import create_async_redis

logger = logging.getLogger(__name__)

# JSON-RPC reserves -32000 to -32099 for implementation-defined server errors.
POLICY_DENIED_ERROR_CODE = -32001
UPSTREAM_ERROR_CODE = -32002
HITL_DENIED_ERROR_CODE = -32003
HITL_TIMEOUT_ERROR_CODE = -32004

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
    config_path: Path | str | None = None,
    policy_dir: Path | str | None = None,
    database_url: str | None = None,
    redis_url: str | None = None,
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.routing = load_routing_table(config_path or settings.config_path)
        app.state.policy_engine = PolicyEngine(
            load_policy_pack(policy_dir or settings.policy_dir)
        )
        app.state.rate_limiter = RateLimiter()
        app.state.http_client = httpx.AsyncClient()
        engine = create_engine(database_url or settings.database_url)
        session_factory = create_session_factory(engine)
        app.state.audit_store = AuditStore(session_factory)
        app.state.db_engine = engine
        app.state.redis = create_async_redis(redis_url or settings.redis_url)

        app.state.event_bus = EventBus()
        control_plane_graph = build_graph(session_factory, app.state.redis)
        control_plane_task = asyncio.create_task(
            run_forever(app.state.event_bus, control_plane_graph)
        )

        logger.info("gateway.started routes=%s", list(app.state.routing.servers.keys()))
        try:
            yield
        finally:
            control_plane_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await control_plane_task
            await app.state.http_client.aclose()
            await app.state.redis.aclose()
            await engine.dispose()

    app = FastAPI(title="Interpose gateway", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> Response:
        # Liveness: the process is up and serving HTTP at all. Deliberately checks
        # nothing external -- that's /readyz's job. A liveness probe that depends on
        # Postgres/Redis would make Kubernetes restart a perfectly healthy gateway pod
        # during a transient DB blip, which is the wrong response to that failure.
        return JSONResponse({"status": "ok"})

    @app.get("/readyz")
    async def readyz(request: Request) -> Response:
        checks = await _readiness_checks(request.app)
        status_code = 200 if all(checks.values()) else 503
        return JSONResponse(checks, status_code=status_code)

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


async def _readiness_checks(app: FastAPI) -> dict[str, bool]:
    """Section 11.5's readiness probe: gateway is ready only if it can actually reach
    both stateful dependencies it needs on the hot path (audit writes, HITL/session
    state) -- not just that the process started."""
    postgres_ok = False
    try:
        async with app.state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:
        logger.warning("gateway.readyz_postgres_unreachable", exc_info=True)

    redis_ok = False
    try:
        await app.state.redis.ping()
        redis_ok = True
    except Exception:
        logger.warning("gateway.readyz_redis_unreachable", exc_info=True)

    return {"postgres": postgres_ok, "redis": redis_ok}


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
        denied = await audit_store.write_entry(
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
        await _publish_decision_event(
            request,
            audit_id=denied.id,
            trace_id=trace_id,
            subject=subject,
            session_id=session_id,
            server_name=server_name,
            tool_name=tool_name,
            args_hash=args_hash,
            policies_fired=policies_fired,
            decision_payload=_decision_payload(decision),
        )
        return _policy_denied_response(rpc_id, decision)

    if decision.outcome is Outcome.HOLD:
        return await _handle_hold(
            request=request,
            decision=decision,
            trace_id=trace_id,
            args_hash=args_hash,
            subject=subject,
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            rpc_id=rpc_id,
            session_id=session_id,
            policies_fired=policies_fired,
            upstream_url=upstream_url,
            forward_headers=forward_headers,
            body=body,
            request_id=request_id,
        )

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
    await _publish_decision_event(
        request,
        audit_id=intent.id,
        trace_id=trace_id,
        subject=subject,
        session_id=session_id,
        server_name=server_name,
        tool_name=tool_name,
        args_hash=args_hash,
        policies_fired=policies_fired,
        decision_payload=_decision_payload(decision),
    )

    return await _forward_and_record(
        client=client,
        audit_store=audit_store,
        method=request.method,
        upstream_url=upstream_url,
        forward_headers=forward_headers,
        body=body,
        request_id=request_id,
        parent_id=intent.id,
        trace_id=trace_id,
        subject=subject,
        session_id=session_id,
        server_name=server_name,
        tool_name=tool_name,
        args_hash=args_hash,
        arguments=arguments,
        policies_fired=policies_fired,
        decision_payload=_decision_payload(decision),
        rpc_id=rpc_id,
    )


async def _handle_hold(
    *,
    request: Request,
    decision: PolicyDecision,
    trace_id: uuid.UUID,
    args_hash: str,
    subject: str,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    rpc_id: str | int,
    session_id: str,
    policies_fired: list[dict[str, str]],
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    request_id: str,
) -> Response:
    audit_store: AuditStore = request.app.state.audit_store
    client: httpx.AsyncClient = request.app.state.http_client
    redis_conn = request.app.state.redis
    reviewer_group = decision.reviewer_group or "unspecified"
    timeout_seconds = decision.timeout_seconds or 0

    held = await audit_store.write_entry(
        status="HELD",
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
    ticket = await hitl.create_ticket(
        redis_conn,
        server=server_name,
        tool=tool_name,
        arguments=arguments,
        agent_id=subject,
        session_id=session_id,
        trace_id=str(trace_id),
        audit_entry_id=held.id,
        reviewer_group=reviewer_group,
        timeout_seconds=timeout_seconds,
    )
    await _publish_decision_event(
        request,
        audit_id=held.id,
        trace_id=trace_id,
        subject=subject,
        session_id=session_id,
        server_name=server_name,
        tool_name=tool_name,
        args_hash=args_hash,
        policies_fired=policies_fired,
        decision_payload=_decision_payload(decision),
        hitl_ticket_id=uuid.UUID(ticket.ticket_id),
    )
    logger.info(
        "gateway.hitl_held request_id=%s ticket_id=%s server=%s tool=%s reviewer_group=%s "
        "timeout_seconds=%d",
        request_id,
        ticket.ticket_id,
        server_name,
        tool_name,
        reviewer_group,
        timeout_seconds,
    )

    resolved = await hitl.wait_for_decision(redis_conn, ticket.ticket_id, timeout_seconds)

    if resolved is None or resolved.status == "PENDING":
        logger.warning(
            "gateway.hitl_timeout request_id=%s ticket_id=%s", request_id, ticket.ticket_id
        )
        await audit_store.write_entry(
            status="DENIED",
            trace_id=trace_id,
            span_id=uuid.uuid4(),
            parent_id=held.id,
            agent_id=subject,
            session_id=session_id,
            server=server_name,
            tool=tool_name,
            args_hash=args_hash,
            args_redacted=arguments,
            policies_fired=policies_fired,
            decision={
                "outcome": "DENY",
                "fired_policy": decision.fired_policy,
                "reason": "hitl_timeout",
            },
            hitl_ticket_id=uuid.UUID(ticket.ticket_id),
        )
        return _error_response(
            rpc_id,
            HITL_TIMEOUT_ERROR_CODE,
            "hitl_timeout",
            {"ticket_id": ticket.ticket_id, "reviewer_group": reviewer_group},
        )

    if resolved.status == "DENIED":
        logger.info(
            "gateway.hitl_denied request_id=%s ticket_id=%s decided_by=%s",
            request_id,
            ticket.ticket_id,
            resolved.decided_by,
        )
        await audit_store.write_entry(
            status="DENIED",
            trace_id=trace_id,
            span_id=uuid.uuid4(),
            parent_id=held.id,
            agent_id=subject,
            session_id=session_id,
            server=server_name,
            tool=tool_name,
            args_hash=args_hash,
            args_redacted=arguments,
            policies_fired=policies_fired,
            decision={
                "outcome": "DENY",
                "fired_policy": decision.fired_policy,
                "reason": "hitl_denied",
            },
            hitl_ticket_id=uuid.UUID(ticket.ticket_id),
            hitl_reviewer=resolved.decided_by,
            hitl_decision=resolved.status,
            hitl_rationale=resolved.rationale,
        )
        return _error_response(
            rpc_id,
            HITL_DENIED_ERROR_CODE,
            "hitl_denied",
            {
                "ticket_id": ticket.ticket_id,
                "reviewer": resolved.decided_by,
                "rationale": resolved.rationale,
            },
        )

    # APPROVED -- proceed exactly like a PASS, linked back to the HELD entry.
    logger.info(
        "gateway.hitl_approved request_id=%s ticket_id=%s decided_by=%s",
        request_id,
        ticket.ticket_id,
        resolved.decided_by,
    )
    return await _forward_and_record(
        client=client,
        audit_store=audit_store,
        method=request.method,
        upstream_url=upstream_url,
        forward_headers=forward_headers,
        body=body,
        request_id=request_id,
        parent_id=held.id,
        trace_id=trace_id,
        subject=subject,
        session_id=session_id,
        server_name=server_name,
        tool_name=tool_name,
        args_hash=args_hash,
        arguments=arguments,
        policies_fired=policies_fired,
        decision_payload=_decision_payload(decision),
        rpc_id=rpc_id,
        hitl_ticket_id=uuid.UUID(ticket.ticket_id),
        hitl_reviewer=resolved.decided_by,
        hitl_decision=resolved.status,
        hitl_rationale=resolved.rationale,
    )


async def _forward_and_record(
    *,
    client: httpx.AsyncClient,
    audit_store: AuditStore,
    method: str,
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    request_id: str,
    parent_id: int,
    trace_id: uuid.UUID,
    subject: str,
    session_id: str,
    server_name: str,
    tool_name: str,
    args_hash: str,
    arguments: dict[str, Any],
    policies_fired: list[dict[str, str]],
    decision_payload: dict[str, Any],
    rpc_id: str | int,
    hitl_ticket_id: uuid.UUID | None = None,
    hitl_reviewer: str | None = None,
    hitl_decision: str | None = None,
    hitl_rationale: str | None = None,
) -> Response:
    """Shared by the PASS path and a HITL-approved hold: forward to upstream, then
    write the COMPLETED/UPSTREAM_ERROR audit row linked to whatever came before it
    (an INTENT row for a plain PASS, a HELD row for an approved hold)."""
    start = time.monotonic()
    try:
        response = await _forward(client, method, upstream_url, forward_headers, body, request_id)
    except httpx.HTTPError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("gateway.upstream_error request_id=%s", request_id)
        await audit_store.write_entry(
            status="UPSTREAM_ERROR",
            trace_id=trace_id,
            span_id=uuid.uuid4(),
            parent_id=parent_id,
            agent_id=subject,
            session_id=session_id,
            server=server_name,
            tool=tool_name,
            args_hash=args_hash,
            args_redacted=arguments,
            policies_fired=policies_fired,
            decision={"outcome": "UPSTREAM_ERROR", "detail": str(exc)},
            latency_ms=latency_ms,
            hitl_ticket_id=hitl_ticket_id,
            hitl_reviewer=hitl_reviewer,
            hitl_decision=hitl_decision,
            hitl_rationale=hitl_rationale,
        )
        return _upstream_error_response(rpc_id, exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    # Latency measures time-to-response-headers, not full body consumption (see
    # _forward) -- and for a held call, not the time spent waiting on HITL review
    # either, which is tracked separately via the HELD/COMPLETED audit timestamps.
    await audit_store.write_entry(
        status="COMPLETED",
        trace_id=trace_id,
        span_id=uuid.uuid4(),
        parent_id=parent_id,
        agent_id=subject,
        session_id=session_id,
        server=server_name,
        tool=tool_name,
        args_hash=args_hash,
        args_redacted=arguments,
        policies_fired=policies_fired,
        decision=decision_payload,
        latency_ms=latency_ms,
        hitl_ticket_id=hitl_ticket_id,
        hitl_reviewer=hitl_reviewer,
        hitl_decision=hitl_decision,
        hitl_rationale=hitl_rationale,
    )
    return response


def _decision_payload(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "outcome": decision.outcome.value,
        "fired_policy": decision.fired_policy,
        "reason": decision.reason,
    }


async def _publish_decision_event(
    request: Request,
    *,
    audit_id: int,
    trace_id: uuid.UUID,
    subject: str,
    session_id: str,
    server_name: str,
    tool_name: str,
    args_hash: str,
    policies_fired: list[dict[str, str]],
    decision_payload: dict[str, Any],
    hitl_ticket_id: uuid.UUID | None = None,
) -> None:
    """Publishes a DecisionEvent to the control plane (Section 7.4) -- once per
    decision-defining audit write (DENIED, HELD, or INTENT), never for the
    COMPLETED/UPSTREAM_ERROR follow-ups those produce, since the decision itself
    already got published when the row it's linked to was written."""
    event_bus: EventBus = request.app.state.event_bus
    event = DecisionEvent(
        audit_id=audit_id,
        trace_id=trace_id,
        agent_id=subject,
        session_id=session_id,
        server=server_name,
        tool=tool_name,
        args_hash=args_hash,
        policies_fired=[PolicyResult(**p) for p in policies_fired],
        decision=CPDecision(**decision_payload),
        hitl_ticket_id=hitl_ticket_id,
        timestamp=datetime.now(UTC),
    )
    await event_bus.publish(event)


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
    return _error_response(
        rpc_id,
        POLICY_DENIED_ERROR_CODE,
        "policy_denied",
        {"policy": decision.fired_policy, "reason": decision.reason},
    )


def _upstream_error_response(rpc_id: str | int, exc: Exception) -> Response:
    return _error_response(rpc_id, UPSTREAM_ERROR_CODE, "upstream_error", {"detail": str(exc)})


def _error_response(rpc_id: str | int, code: int, message: str, data: dict[str, Any]) -> Response:
    error = JSONRPCError(
        jsonrpc="2.0", id=rpc_id, error=ErrorData(code=code, message=message, data=data)
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
