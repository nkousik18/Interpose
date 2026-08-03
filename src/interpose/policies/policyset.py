"""In-memory PolicySet compilation and evaluation.

Covers Stage 4 (policy compilation), Stage 5 (request-side policy evaluation), and --
new as of Phase 3 Day 14 -- Stage 8 (response-side policy evaluation) from
docs/INTERPOSE_SCOPING.md Section 6.5.

Request-side (`evaluate`, Stage 5): `allowlist -> denylist -> rate_limit -> custom
(request-stage) -> hitl_gate`. Response-side (`evaluate_response`, Stage 8):
`pii_redaction` and `custom` (response-stage) policies, applied to the upstream
response after it's back but before it reaches the calling agent.

`evaluate` is `async` (unlike Phase 1-3's synchronous version) because a request-stage
custom policy can need real I/O -- `aml-sanctions-required` queries the audit log.

Allowlist semantics, spelled out because they're not obvious from the schema alone:
an allowlist policy for a server doesn't just grant its own tools -- its presence
flips that *server* to default-deny. If `transaction-graph` has one allowlist policy
naming `read_balance`, then `read_balance` passes, but `mark_investigated` is denied
even though nothing ever wrote a denylist rule for it. A server with no allowlist
policy at all is unaffected -- default-allow, same as before any policy existed. This
mirrors how allow-lists work in most real gateways (security groups, K8s
NetworkPolicy): writing the first allow rule for a scope is what turns on enforcement
for that scope.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from interpose.policies.custom import (
    REQUEST_POLICIES,
    RESPONSE_POLICIES,
    RequestPolicyContext,
    ResponsePolicyContext,
    UnknownCustomPolicyError,
)
from interpose.policies.redaction import redact_json_value
from interpose.policies.schema import (
    EFFECT_ORDER,
    AllowlistEffect,
    CostCapEffect,
    CustomEffect,
    DenylistEffect,
    HitlGateEffect,
    PiiRedactionEffect,
    Policy,
    RateLimitEffect,
)


class Outcome(StrEnum):
    PASS = "PASS"
    DENY = "DENY"
    HOLD = "HOLD"


@dataclass(frozen=True)
class PolicyDecision:
    outcome: Outcome
    fired_policy: str | None = None
    reason: str | None = None
    # Only set when outcome is HOLD -- what the gateway needs to open a HITL ticket.
    reviewer_group: str | None = None
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class ResponseEvaluationResult:
    """Stage 8's output: the (possibly redacted) response payload to re-serialize
    back to the agent, plus any tags response-side policies contributed."""

    payload: Any
    tags: list[str] = field(default_factory=list)


class RateLimiter:
    """In-memory fixed-window rate limiter.

    Stand-in for the Redis-backed sliding-window limiter in Section 6.8 (C4) -- same
    check-and-increment interface, so swapping the implementation later won't touch
    policy evaluation code. Not safe across multiple processes; fine for a
    single-process MVP.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._windows: dict[tuple[str, str], tuple[int, float]] = {}

    def check_and_increment(self, key: tuple[str, str], limit: int, window_seconds: int) -> bool:
        """Count this call against `key`'s window. Returns False if it's over `limit`."""
        now = self._clock()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= window_seconds:
            count, window_start = 0, now
        count += 1
        self._windows[key] = (count, window_start)
        return count <= limit


class PolicySet:
    """The ordered policies that apply to one {server, tool} pair."""

    def __init__(self, policies: list[Policy], server_has_allowlist: bool) -> None:
        self._policies = policies
        self._server_has_allowlist = server_has_allowlist

    @property
    def policies(self) -> tuple[Policy, ...]:
        """Applicable policies in evaluation order (for logging/audit, and tests)."""
        return tuple(self._policies)

    @property
    def static_tags(self) -> list[str]:
        """Every applicable policy's `audit.tag` values, deduped -- independent of
        which policy "wins" the PASS/DENY/HOLD decision. This is what makes
        `tag_only` policies like `aml-audit-tagging` work: they never win the
        decision (they have no gating behavior at all), but their tags still land on
        every matching audit entry."""
        tags: list[str] = []
        for policy in self._policies:
            for tag in policy.audit.tag:
                if tag not in tags:
                    tags.append(tag)
        return tags

    async def evaluate(
        self,
        rate_limiter: RateLimiter,
        subject: str = "global",
        request_context: RequestPolicyContext | None = None,
    ) -> PolicyDecision:
        allow_hit = next((p for p in self._policies if isinstance(p.effect, AllowlistEffect)), None)
        if allow_hit is not None:
            return PolicyDecision(Outcome.PASS, allow_hit.policy, "allowlisted")
        if self._server_has_allowlist:
            return PolicyDecision(Outcome.DENY, None, "not_on_allowlist")

        for policy in self._policies:
            if isinstance(policy.effect, DenylistEffect):
                return PolicyDecision(Outcome.DENY, policy.policy, policy.effect.reason)

        for policy in self._policies:
            effect = policy.effect
            if isinstance(effect, RateLimitEffect):
                key = (policy.policy, subject)
                if not rate_limiter.check_and_increment(key, effect.limit, effect.window_seconds):
                    return PolicyDecision(Outcome.DENY, policy.policy, "rate_limit_exceeded")

        for policy in self._policies:
            effect = policy.effect
            if isinstance(effect, CustomEffect) and effect.stage == "request":
                fn = REQUEST_POLICIES.get(effect.name)
                if fn is None:
                    raise UnknownCustomPolicyError(
                        f"policy {policy.policy!r} references unknown request-side "
                        f"custom policy {effect.name!r}"
                    )
                if request_context is None:
                    raise ValueError(
                        f"policy {policy.policy!r} needs a RequestPolicyContext but "
                        "none was provided"
                    )
                reason = await fn(policy, request_context)
                if reason is not None:
                    return PolicyDecision(Outcome.DENY, policy.policy, reason)

        for policy in self._policies:
            effect = policy.effect
            if isinstance(effect, HitlGateEffect):
                return PolicyDecision(
                    Outcome.HOLD,
                    policy.policy,
                    "hitl_required",
                    reviewer_group=effect.reviewer_group,
                    timeout_seconds=effect.timeout_seconds,
                )

        for policy in self._policies:
            if isinstance(policy.effect, CostCapEffect):
                raise NotImplementedError(
                    f"cost_cap policies are not enforced yet (policy {policy.policy!r}) -- "
                    "the gateway has no visibility into LLM token cost, only tool-call "
                    "volume; see schema.CostCapEffect's docstring"
                )

        return PolicyDecision(Outcome.PASS)

    async def evaluate_response(
        self, payload: Any, response_context: ResponsePolicyContext
    ) -> ResponseEvaluationResult:
        """Stage 8: redact PII from `payload` (the tool's parsed `structuredContent`
        or `content`) and run any response-stage custom policies. Only called for
        calls that reached PASS or an approved HOLD -- there's no response to
        evaluate for a DENY."""
        tags: list[str] = []

        pattern_names: list[str] = []
        for policy in self._policies:
            if isinstance(policy.effect, PiiRedactionEffect):
                pattern_names.extend(policy.effect.patterns)
        if pattern_names:
            payload = redact_json_value(payload, pattern_names)

        for policy in self._policies:
            effect = policy.effect
            if isinstance(effect, CustomEffect) and effect.stage == "response":
                fn = RESPONSE_POLICIES.get(effect.name)
                if fn is None:
                    raise UnknownCustomPolicyError(
                        f"policy {policy.policy!r} references unknown response-side "
                        f"custom policy {effect.name!r}"
                    )
                tags.extend(await fn(policy, response_context))

        return ResponseEvaluationResult(payload=payload, tags=tags)

    @property
    def has_response_side_policies(self) -> bool:
        """Whether this PolicySet needs Stage 8 evaluation at all -- the gateway uses
        this to decide whether a call's response must be buffered and parsed
        (needed for redaction/response-stage custom policies) or can stay a plain
        streamed passthrough (every server/tool with no such policy, which is most
        of them)."""
        return any(
            isinstance(p.effect, PiiRedactionEffect)
            or (isinstance(p.effect, CustomEffect) and p.effect.stage == "response")
            for p in self._policies
        )


class PolicyEngine:
    """Holds a full policy list; compiles and caches a PolicySet per {server, tool}.

    This is the "in-memory cache (invalidated on config reload)" of Stage 4 -- a fresh
    PolicyEngine is built from the reloaded policy list rather than mutating one in
    place, so a reload is an atomic pointer swap (Section 6.6, "policy hot reload").
    """

    def __init__(self, policies: list[Policy]) -> None:
        self._policies = policies
        self._server_has_allowlist = self._compute_server_allowlist_flags(policies)
        self._cache: dict[tuple[str, str], PolicySet] = {}

    def compile(self, server: str, tool: str) -> PolicySet:
        key = (server, tool)
        if key not in self._cache:
            applicable = [p for p in self._policies if p.applies_to.matches(server, tool)]
            applicable.sort(key=lambda p: EFFECT_ORDER.index(p.effect.type))
            # A server-scoped allowlist ("*") only turns on default-deny for the
            # literal server it's declared for, not every server -- a wildcard
            # *tools* match ("*" in applies_to.tools) is orthogonal to that and
            # doesn't change this flag at all.
            self._cache[key] = PolicySet(applicable, self._server_has_allowlist.get(server, False))
        return self._cache[key]

    @staticmethod
    def _compute_server_allowlist_flags(policies: list[Policy]) -> dict[str, bool]:
        flags: dict[str, bool] = {}
        for policy in policies:
            if isinstance(policy.effect, AllowlistEffect):
                flags[policy.applies_to.server] = True
        return flags
