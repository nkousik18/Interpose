"""Named custom-policy plugin registry (docs/INTERPOSE_SCOPING.md Section 9.8,
Phase 3 Day 14). A `CustomEffect` in policy YAML (`interpose.policies.schema`)
references a function here by `name` rather than embedding code directly -- a policy
pack is data a deployer can drop into `config/policies` at runtime, and data that can
execute arbitrary code is a code-injection vector, not a policy. Concrete pack
implementations (e.g. `interpose.policies.packs.aml`) register themselves against this
module's decorators at import time; the gateway imports every known pack module at
startup so `CustomEffect.name` lookups never depend on which specific policy YAML
files happen to be present in a given deployment.

Two dispatch points, matching the two stages a `CustomEffect` can declare:

- Request-side (Stage 5, before forwarding) -- can deny the call, like
  `aml-sanctions-required`.
- Response-side (Stage 8, after the upstream response is available) -- can tag the
  audit entry and cause side effects (e.g. writing to Redis), but can never deny a
  call that's already completed, like `aml-structuring-alert`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.policies.schema import Policy


@dataclass(frozen=True)
class RequestPolicyContext:
    """What a request-side custom policy needs to decide PASS/DENY.
    `session_factory` lets it query the audit log directly -- the same
    synchronous-read-from-Postgres pattern Agent A1 already uses for its own session
    features (interpose.control_plane.agents.policy_evaluator).

    `agent_id`, not `session_id`, is what a cross-server custom policy (like
    `aml-sanctions-required`) should correlate on. `session_id` is the MCP transport's
    `Mcp-Session-Id` -- assigned independently by *each* upstream server during its own
    `initialize` handshake, so a single investigation run talking to two different
    upstream servers gets two different, unrelated session IDs (confirmed live: two
    real connections to two real servers behind this same gateway came back with
    completely different session IDs). `agent_id` (from the `Authorization` header,
    `_extract_agent_id`) is under the *calling agent's* control and can be kept
    consistent across every connection it opens, which is what actually makes
    "did this investigation already check sanctions" answerable at all."""

    session_id: str
    agent_id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    session_factory: async_sessionmaker


@dataclass(frozen=True)
class ResponsePolicyContext:
    """What a response-side custom policy needs. `response_payload` is the tool's
    parsed `structuredContent` (or `None` if the response wasn't JSON, or was an
    error) -- never the raw bytes, so a custom policy never has to know about the
    MCP envelope or FastMCP's `structuredContent` unwrapping quirk itself
    (concepts/28)."""

    session_id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    response_payload: Any
    redis: Redis


# A request-side function returns a deny reason if it fires, or None to pass through
# to whatever the engine would otherwise have decided.
RequestPolicyFn = Callable[[Policy, RequestPolicyContext], Awaitable[str | None]]
# A response-side function returns tags to merge into the audit entry being written;
# side effects (e.g. setting a Redis flag) happen inside the function itself.
ResponsePolicyFn = Callable[[Policy, ResponsePolicyContext], Awaitable[list[str]]]

REQUEST_POLICIES: dict[str, RequestPolicyFn] = {}
RESPONSE_POLICIES: dict[str, ResponsePolicyFn] = {}


def register_request_policy(name: str) -> Callable[[RequestPolicyFn], RequestPolicyFn]:
    def decorator(fn: RequestPolicyFn) -> RequestPolicyFn:
        if name in REQUEST_POLICIES:
            raise ValueError(f"a request-side custom policy named {name!r} is already registered")
        REQUEST_POLICIES[name] = fn
        return fn

    return decorator


def register_response_policy(name: str) -> Callable[[ResponsePolicyFn], ResponsePolicyFn]:
    def decorator(fn: ResponsePolicyFn) -> ResponsePolicyFn:
        if name in RESPONSE_POLICIES:
            raise ValueError(f"a response-side custom policy named {name!r} is already registered")
        RESPONSE_POLICIES[name] = fn
        return fn

    return decorator


class UnknownCustomPolicyError(Exception):
    """Raised when a `CustomEffect.name` doesn't match anything registered -- a
    misconfigured pack (a typo, or a pack module that was never imported) should
    fail loudly and fail-closed, not silently pass every call through."""
