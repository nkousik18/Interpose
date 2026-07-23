"""In-memory PolicySet compilation and evaluation.

Covers Stage 4 (policy compilation) and Stage 5 (policy evaluation) from
docs/INTERPOSE_SCOPING.md Section 6.5, for four of the five effect types: allowlist,
denylist, rate_limit, and (as of Phase 2 Day 6) hitl_gate, which produces a HOLD
outcome carrying enough information for the gateway to open a ticket
(`interpose.session.hitl`). `pii_redaction` still just parses (schema.py) --
`PolicySet.evaluate` raises `NotImplementedError` if it shows up in an applicable
policy set, rather than silently letting the call through as if the policy didn't
exist.

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
from dataclasses import dataclass
from enum import StrEnum

from interpose.policies.schema import (
    EFFECT_ORDER,
    AllowlistEffect,
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

    def evaluate(self, rate_limiter: RateLimiter, subject: str = "global") -> PolicyDecision:
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
            if isinstance(policy.effect, PiiRedactionEffect):
                raise NotImplementedError(
                    f"pii_redaction policies are not enforced yet (policy "
                    f"{policy.policy!r}); schema-only as of Phase 1 Day 3"
                )

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

        return PolicyDecision(Outcome.PASS)


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
            self._cache[key] = PolicySet(applicable, self._server_has_allowlist.get(server, False))
        return self._cache[key]

    @staticmethod
    def _compute_server_allowlist_flags(policies: list[Policy]) -> dict[str, bool]:
        flags: dict[str, bool] = {}
        for policy in policies:
            if isinstance(policy.effect, AllowlistEffect):
                flags[policy.applies_to.server] = True
        return flags
