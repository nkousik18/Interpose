"""Unit tests for interpose.policies.policyset -- compilation, caching, and the
allowlist/denylist/rate_limit/custom/hitl_gate composition rules from Section 6.5
Stage 5. Response-side evaluation (pii_redaction, response-stage custom policies) and
custom-policy dispatch mechanics are covered separately in test_custom_dispatch.py.
"""

import pytest

from interpose.policies.policyset import Outcome, PolicyEngine, RateLimiter
from interpose.policies.schema import Policy


def _policy(name: str, server: str, tools: list[str], effect: dict) -> Policy:
    return Policy.model_validate(
        {"policy": name, "applies_to": {"server": server, "tools": tools}, "effect": effect}
    )


def allowlist(name: str, server: str, tools: list[str]) -> Policy:
    return _policy(name, server, tools, {"type": "allowlist"})


def denylist(name: str, server: str, tools: list[str], reason: str = "denylisted") -> Policy:
    return _policy(name, server, tools, {"type": "denylist", "reason": reason})


def rate_limit(
    name: str, server: str, tools: list[str], limit: int, window_seconds: int
) -> Policy:
    effect = {"type": "rate_limit", "limit": limit, "window_seconds": window_seconds}
    return _policy(name, server, tools, effect)


def hitl_gate(name: str, server: str, tools: list[str]) -> Policy:
    effect = {"type": "hitl_gate", "reviewer_group": "aml-analysts", "timeout_seconds": 3600}
    return _policy(name, server, tools, effect)


def cost_cap(name: str, server: str, tools: list[str]) -> Policy:
    return _policy(name, server, tools, {"type": "cost_cap", "session_limit_usd": 2.0})


class TestHitlGate:
    async def test_matching_tool_holds_with_reviewer_group_and_timeout(self) -> None:
        policy = hitl_gate("h1", "transaction-graph", ["mark_investigated"])
        engine = PolicyEngine([policy])
        policy_set = engine.compile("transaction-graph", "mark_investigated")
        decision = await policy_set.evaluate(RateLimiter())
        assert decision.outcome == Outcome.HOLD
        assert decision.fired_policy == "h1"
        assert decision.reviewer_group == "aml-analysts"
        assert decision.timeout_seconds == 3600

    async def test_unlisted_tool_is_unaffected(self) -> None:
        policy = hitl_gate("h1", "transaction-graph", ["mark_investigated"])
        engine = PolicyEngine([policy])
        decision = await engine.compile("transaction-graph", "read_balance").evaluate(
            RateLimiter()
        )
        assert decision.outcome == Outcome.PASS

    async def test_denylist_still_short_circuits_before_hitl_gate(self) -> None:
        policies = [
            denylist("d1", "transaction-graph", ["mark_investigated"]),
            hitl_gate("h1", "transaction-graph", ["mark_investigated"]),
        ]
        engine = PolicyEngine(policies)
        policy_set = engine.compile("transaction-graph", "mark_investigated")
        decision = await policy_set.evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"

    async def test_rate_limit_still_evaluated_before_hitl_gate(self) -> None:
        rate_limited = rate_limit(
            "r1", "transaction-graph", ["mark_investigated"], limit=1, window_seconds=60
        )
        policies = [
            rate_limited,
            hitl_gate("h1", "transaction-graph", ["mark_investigated"]),
        ]
        engine = PolicyEngine(policies)
        policy_set = engine.compile("transaction-graph", "mark_investigated")
        limiter = RateLimiter()
        first = await policy_set.evaluate(limiter)
        assert first.outcome == Outcome.HOLD  # under the rate limit, falls through to hitl_gate
        second = await policy_set.evaluate(limiter)
        assert second.outcome == Outcome.DENY  # now over the rate limit
        assert second.fired_policy == "r1"


class TestDefaultAllow:
    async def test_no_policies_at_all_passes(self) -> None:
        engine = PolicyEngine([])
        decision = await engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS
        assert decision.fired_policy is None

    async def test_policies_on_other_servers_do_not_affect_this_one(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["*"])])
        decision = await engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS


class TestAllowlist:
    async def test_matching_tool_passes(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["check_name"])])
        decision = await engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS
        assert decision.fired_policy == "a1"
        assert decision.reason == "allowlisted"

    async def test_presence_of_allowlist_denies_unlisted_tool_on_same_server(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["check_name"])])
        decision = await engine.compile("ofac-sanctions", "some_other_tool").evaluate(
            RateLimiter()
        )
        assert decision.outcome == Outcome.DENY
        assert decision.reason == "not_on_allowlist"

    async def test_wildcard_allowlist_covers_every_tool(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["*"])])
        decision = await engine.compile("ofac-sanctions", "anything").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS


class TestDenylist:
    async def test_matching_tool_is_denied_with_reason(self) -> None:
        policy = denylist("d1", "transaction-graph", ["delete_record"], "irreversible")
        engine = PolicyEngine([policy])
        decision = await engine.compile("transaction-graph", "delete_record").evaluate(
            RateLimiter()
        )
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"
        assert decision.reason == "irreversible"

    async def test_unlisted_tool_is_unaffected(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["delete_record"])])
        decision = await engine.compile("transaction-graph", "read_balance").evaluate(
            RateLimiter()
        )
        assert decision.outcome == Outcome.PASS

    async def test_denylist_short_circuits_before_rate_limit(self) -> None:
        policies = [
            denylist("d1", "transaction-graph", ["delete_record"]),
            rate_limit("r1", "transaction-graph", ["delete_record"], limit=1, window_seconds=60),
        ]
        engine = PolicyEngine(policies)
        policy_set = engine.compile("transaction-graph", "delete_record")
        decision = await policy_set.evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"


class TestRateLimit:
    async def test_under_limit_passes(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=2, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()
        assert (await policy_set.evaluate(limiter)).outcome == Outcome.PASS
        assert (await policy_set.evaluate(limiter)).outcome == Outcome.PASS

    async def test_exceeding_limit_denies(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()
        assert (await policy_set.evaluate(limiter)).outcome == Outcome.PASS
        second = await policy_set.evaluate(limiter)
        assert second.outcome == Outcome.DENY
        assert second.fired_policy == "r1"
        assert second.reason == "rate_limit_exceeded"

    async def test_window_resets_after_expiry(self) -> None:
        clock = {"t": 0.0}
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=10)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter(clock=lambda: clock["t"])

        assert (await policy_set.evaluate(limiter)).outcome == Outcome.PASS
        assert (await policy_set.evaluate(limiter)).outcome == Outcome.DENY

        clock["t"] = 11.0
        assert (await policy_set.evaluate(limiter)).outcome == Outcome.PASS

    async def test_separate_subjects_have_independent_limits(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()

        assert (await policy_set.evaluate(limiter, subject="agent-a")).outcome == Outcome.PASS
        assert (await policy_set.evaluate(limiter, subject="agent-b")).outcome == Outcome.PASS
        assert (await policy_set.evaluate(limiter, subject="agent-a")).outcome == Outcome.DENY


class TestCompilation:
    def test_compiled_policy_set_is_cached(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["*"])])
        first = engine.compile("transaction-graph", "delete_record")
        second = engine.compile("transaction-graph", "delete_record")
        assert first is second

    def test_evaluation_order_is_allowlist_denylist_rate_limit_hitl_gate(self) -> None:
        policies = [
            hitl_gate("h1", "s", ["*"]),
            rate_limit("r1", "s", ["*"], limit=5, window_seconds=60),
            denylist("d1", "s", ["*"]),
            allowlist("a1", "s", ["*"]),
        ]
        engine = PolicyEngine(policies)
        ordered_names = [p.policy for p in engine.compile("s", "tool").policies]
        assert ordered_names == ["a1", "d1", "r1", "h1"]

    def test_only_applicable_policies_are_included(self) -> None:
        policies = [
            denylist("d1", "s", ["tool-a"]),
            denylist("d2", "s", ["tool-b"]),
        ]
        engine = PolicyEngine(policies)
        ordered_names = [p.policy for p in engine.compile("s", "tool-a").policies]
        assert ordered_names == ["d1"]

    def test_wildcard_server_policy_applies_everywhere(self) -> None:
        engine = PolicyEngine([denylist("d1", "*", ["*"])])
        ordered_names_a = [p.policy for p in engine.compile("ofac-sanctions", "x").policies]
        ordered_names_b = [p.policy for p in engine.compile("transaction-graph", "y").policies]
        assert ordered_names_a == ["d1"]
        assert ordered_names_b == ["d1"]


class TestStaticTags:
    def test_no_tags_by_default(self) -> None:
        engine = PolicyEngine([denylist("d1", "s", ["*"])])
        assert engine.compile("s", "tool").static_tags == []

    def test_collects_tags_from_every_applicable_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "tagged",
                "applies_to": {"server": "s", "tools": ["*"]},
                "effect": {"type": "tag_only"},
                "audit": {"tag": ["pack:aml", "regulation:BSA"]},
            }
        )
        engine = PolicyEngine([policy])
        assert engine.compile("s", "tool").static_tags == ["pack:aml", "regulation:BSA"]

    def test_deduplicates_repeated_tags_across_policies(self) -> None:
        def tag_policy(name: str) -> Policy:
            return Policy.model_validate(
                {
                    "policy": name,
                    "applies_to": {"server": "s", "tools": ["*"]},
                    "effect": {"type": "tag_only"},
                    "audit": {"tag": ["pack:aml"]},
                }
            )

        engine = PolicyEngine([tag_policy("t1"), tag_policy("t2")])
        assert engine.compile("s", "tool").static_tags == ["pack:aml"]


class TestCostCapStub:
    async def test_raises_not_implemented(self) -> None:
        engine = PolicyEngine([cost_cap("c1", "ofac-sanctions", ["*"])])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        with pytest.raises(NotImplementedError, match="cost_cap"):
            await policy_set.evaluate(RateLimiter())
