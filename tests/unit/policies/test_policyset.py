"""Unit tests for interpose.policies.policyset -- compilation, caching, and the
allowlist/denylist/rate_limit composition rules from Section 6.5 Stage 5 / 6.6.
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


def pii_redaction(name: str, server: str, tools: list[str]) -> Policy:
    return _policy(name, server, tools, {"type": "pii_redaction", "patterns": ["email"]})


class TestUnimplementedEffects:
    def test_hitl_gate_raises_not_implemented(self) -> None:
        engine = PolicyEngine([hitl_gate("h1", "transaction-graph", ["mark_investigated"])])
        policy_set = engine.compile("transaction-graph", "mark_investigated")
        with pytest.raises(NotImplementedError, match="hitl_gate"):
            policy_set.evaluate(RateLimiter())

    def test_pii_redaction_raises_not_implemented(self) -> None:
        engine = PolicyEngine([pii_redaction("p1", "ofac-sanctions", ["check_name"])])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        with pytest.raises(NotImplementedError, match="pii_redaction"):
            policy_set.evaluate(RateLimiter())

    def test_denylist_still_short_circuits_before_unimplemented_hitl_gate(self) -> None:
        policies = [
            denylist("d1", "transaction-graph", ["mark_investigated"]),
            hitl_gate("h1", "transaction-graph", ["mark_investigated"]),
        ]
        engine = PolicyEngine(policies)
        policy_set = engine.compile("transaction-graph", "mark_investigated")
        decision = policy_set.evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"


class TestDefaultAllow:
    def test_no_policies_at_all_passes(self) -> None:
        engine = PolicyEngine([])
        decision = engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS
        assert decision.fired_policy is None

    def test_policies_on_other_servers_do_not_affect_this_one(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["*"])])
        decision = engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS


class TestAllowlist:
    def test_matching_tool_passes(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["check_name"])])
        decision = engine.compile("ofac-sanctions", "check_name").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS
        assert decision.fired_policy == "a1"
        assert decision.reason == "allowlisted"

    def test_presence_of_allowlist_denies_unlisted_tool_on_same_server(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["check_name"])])
        decision = engine.compile("ofac-sanctions", "some_other_tool").evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.reason == "not_on_allowlist"

    def test_wildcard_allowlist_covers_every_tool(self) -> None:
        engine = PolicyEngine([allowlist("a1", "ofac-sanctions", ["*"])])
        decision = engine.compile("ofac-sanctions", "anything").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS


class TestDenylist:
    def test_matching_tool_is_denied_with_reason(self) -> None:
        policy = denylist("d1", "transaction-graph", ["delete_record"], "irreversible")
        engine = PolicyEngine([policy])
        decision = engine.compile("transaction-graph", "delete_record").evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"
        assert decision.reason == "irreversible"

    def test_unlisted_tool_is_unaffected(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["delete_record"])])
        decision = engine.compile("transaction-graph", "read_balance").evaluate(RateLimiter())
        assert decision.outcome == Outcome.PASS

    def test_denylist_short_circuits_before_rate_limit(self) -> None:
        policies = [
            denylist("d1", "transaction-graph", ["delete_record"]),
            rate_limit("r1", "transaction-graph", ["delete_record"], limit=1, window_seconds=60),
        ]
        engine = PolicyEngine(policies)
        policy_set = engine.compile("transaction-graph", "delete_record")
        decision = policy_set.evaluate(RateLimiter())
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "d1"


class TestRateLimit:
    def test_under_limit_passes(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=2, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()
        assert policy_set.evaluate(limiter).outcome == Outcome.PASS
        assert policy_set.evaluate(limiter).outcome == Outcome.PASS

    def test_exceeding_limit_denies(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()
        assert policy_set.evaluate(limiter).outcome == Outcome.PASS
        second = policy_set.evaluate(limiter)
        assert second.outcome == Outcome.DENY
        assert second.fired_policy == "r1"
        assert second.reason == "rate_limit_exceeded"

    def test_window_resets_after_expiry(self) -> None:
        clock = {"t": 0.0}
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=10)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter(clock=lambda: clock["t"])

        assert policy_set.evaluate(limiter).outcome == Outcome.PASS
        assert policy_set.evaluate(limiter).outcome == Outcome.DENY

        clock["t"] = 11.0
        assert policy_set.evaluate(limiter).outcome == Outcome.PASS

    def test_separate_subjects_have_independent_limits(self) -> None:
        policy = rate_limit("r1", "ofac-sanctions", ["*"], limit=1, window_seconds=60)
        engine = PolicyEngine([policy])
        policy_set = engine.compile("ofac-sanctions", "check_name")
        limiter = RateLimiter()

        assert policy_set.evaluate(limiter, subject="agent-a").outcome == Outcome.PASS
        assert policy_set.evaluate(limiter, subject="agent-b").outcome == Outcome.PASS
        assert policy_set.evaluate(limiter, subject="agent-a").outcome == Outcome.DENY


class TestCompilation:
    def test_compiled_policy_set_is_cached(self) -> None:
        engine = PolicyEngine([denylist("d1", "transaction-graph", ["*"])])
        first = engine.compile("transaction-graph", "delete_record")
        second = engine.compile("transaction-graph", "delete_record")
        assert first is second

    def test_evaluation_order_is_allowlist_then_denylist_then_rate_limit(self) -> None:
        policies = [
            rate_limit("r1", "s", ["*"], limit=5, window_seconds=60),
            denylist("d1", "s", ["*"]),
            allowlist("a1", "s", ["*"]),
        ]
        engine = PolicyEngine(policies)
        ordered_names = [p.policy for p in engine.compile("s", "tool").policies]
        assert ordered_names == ["a1", "d1", "r1"]

    def test_only_applicable_policies_are_included(self) -> None:
        policies = [
            denylist("d1", "s", ["tool-a"]),
            denylist("d2", "s", ["tool-b"]),
        ]
        engine = PolicyEngine(policies)
        ordered_names = [p.policy for p in engine.compile("s", "tool-a").policies]
        assert ordered_names == ["d1"]
