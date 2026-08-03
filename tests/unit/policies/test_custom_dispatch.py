"""Unit tests for the custom-policy dispatch mechanics in
interpose.policies.policyset -- request-side (Stage 5, can DENY) and response-side
(Stage 8, tags + pii_redaction) evaluation. The concrete AML pack functions
(interpose.policies.packs.aml) are exercised in test_packs_aml.py (aml_structuring_alert)
and tests/integration/test_investigation_agent_aml_pack.py (aml_sanctions_required,
which needs a real Postgres -- not meaningfully unit-testable, same reasoning as
Agent A1's own DB-backed feature computation).
"""

import pytest

from interpose.policies.custom import REQUEST_POLICIES, RESPONSE_POLICIES, UnknownCustomPolicyError
from interpose.policies.policyset import Outcome, PolicyEngine, RateLimiter
from interpose.policies.schema import Policy


def _custom_request_policy(name: str, server: str, tools: list[str], fn_name: str) -> Policy:
    return Policy.model_validate(
        {
            "policy": name,
            "applies_to": {"server": server, "tools": tools},
            "effect": {"type": "custom", "name": fn_name, "stage": "request"},
        }
    )


def _custom_response_policy(name: str, server: str, tools: list[str], fn_name: str) -> Policy:
    return Policy.model_validate(
        {
            "policy": name,
            "applies_to": {"server": server, "tools": tools},
            "effect": {"type": "custom", "name": fn_name, "stage": "response"},
        }
    )


def _pii_policy(name: str, server: str, tools: list[str], patterns: list[str]) -> Policy:
    return Policy.model_validate(
        {
            "policy": name,
            "applies_to": {"server": server, "tools": tools},
            "effect": {"type": "pii_redaction", "patterns": patterns},
        }
    )


class TestRequestSideCustomDispatch:
    async def test_passes_through_when_the_function_returns_none(self, monkeypatch) -> None:
        async def always_pass(policy, ctx):
            return None

        monkeypatch.setitem(REQUEST_POLICIES, "always_pass", always_pass)
        policy = _custom_request_policy("c1", "s", ["*"], "always_pass")
        engine = PolicyEngine([policy])
        decision = await engine.compile("s", "tool").evaluate(RateLimiter(), request_context="ctx")
        assert decision.outcome == Outcome.PASS

    async def test_denies_with_the_returned_reason(self, monkeypatch) -> None:
        async def always_deny(policy, ctx):
            return "missing precondition"

        monkeypatch.setitem(REQUEST_POLICIES, "always_deny", always_deny)
        policy = _custom_request_policy("c1", "s", ["*"], "always_deny")
        engine = PolicyEngine([policy])
        decision = await engine.compile("s", "tool").evaluate(RateLimiter(), request_context="ctx")
        assert decision.outcome == Outcome.DENY
        assert decision.fired_policy == "c1"
        assert decision.reason == "missing precondition"

    async def test_unknown_custom_policy_name_raises(self) -> None:
        policy = _custom_request_policy("c1", "s", ["*"], "does_not_exist")
        engine = PolicyEngine([policy])
        with pytest.raises(UnknownCustomPolicyError, match="does_not_exist"):
            await engine.compile("s", "tool").evaluate(RateLimiter(), request_context="ctx")

    async def test_missing_context_raises(self, monkeypatch) -> None:
        async def always_pass(policy, ctx):
            return None

        monkeypatch.setitem(REQUEST_POLICIES, "always_pass", always_pass)
        policy = _custom_request_policy("c1", "s", ["*"], "always_pass")
        engine = PolicyEngine([policy])
        with pytest.raises(ValueError, match="RequestPolicyContext"):
            await engine.compile("s", "tool").evaluate(RateLimiter())

    async def test_denylist_still_short_circuits_before_custom(self, monkeypatch) -> None:
        called = False

        async def spy(policy, ctx):
            nonlocal called
            called = True
            return None

        monkeypatch.setitem(REQUEST_POLICIES, "spy", spy)
        policies = [
            Policy.model_validate(
                {
                    "policy": "d1",
                    "applies_to": {"server": "s", "tools": ["*"]},
                    "effect": {"type": "denylist"},
                }
            ),
            _custom_request_policy("c1", "s", ["*"], "spy"),
        ]
        engine = PolicyEngine(policies)
        decision = await engine.compile("s", "tool").evaluate(RateLimiter(), request_context="ctx")
        assert decision.outcome == Outcome.DENY
        assert called is False


class TestResponseSideEvaluation:
    async def test_pii_redaction_applies_to_the_payload(self) -> None:
        policy = _pii_policy("p1", "s", ["*"], ["ssn"])
        engine = PolicyEngine([policy])
        policy_set = engine.compile("s", "tool")
        result = await policy_set.evaluate_response(
            {"note": "ssn 123-45-6789"}, response_context="ctx"
        )
        assert result.payload == {"note": "ssn [REDACTED]"}
        assert result.tags == []

    async def test_no_pii_policy_leaves_payload_untouched(self) -> None:
        engine = PolicyEngine([])
        policy_set = engine.compile("s", "tool")
        payload = {"note": "ssn 123-45-6789"}
        result = await policy_set.evaluate_response(payload, response_context="ctx")
        assert result.payload == payload

    async def test_response_stage_custom_policy_contributes_tags(self, monkeypatch) -> None:
        async def flags_incident(policy, ctx):
            return ["incident:structuring", "severity:high"]

        monkeypatch.setitem(RESPONSE_POLICIES, "flags_incident", flags_incident)
        policy = _custom_response_policy("c1", "s", ["*"], "flags_incident")
        engine = PolicyEngine([policy])
        result = await engine.compile("s", "tool").evaluate_response({}, response_context="ctx")
        assert result.tags == ["incident:structuring", "severity:high"]

    async def test_unknown_response_side_custom_policy_raises(self) -> None:
        policy = _custom_response_policy("c1", "s", ["*"], "does_not_exist")
        engine = PolicyEngine([policy])
        with pytest.raises(UnknownCustomPolicyError, match="does_not_exist"):
            await engine.compile("s", "tool").evaluate_response({}, response_context="ctx")

    async def test_request_stage_custom_policy_is_not_dispatched_here(self, monkeypatch) -> None:
        called = False

        async def spy(policy, ctx):
            nonlocal called
            called = True
            return None

        monkeypatch.setitem(REQUEST_POLICIES, "spy", spy)
        policy = _custom_request_policy("c1", "s", ["*"], "spy")
        engine = PolicyEngine([policy])
        await engine.compile("s", "tool").evaluate_response({}, response_context="ctx")
        assert called is False


class TestHasResponseSidePolicies:
    def test_false_with_no_policies(self) -> None:
        engine = PolicyEngine([])
        assert engine.compile("s", "tool").has_response_side_policies is False

    def test_true_with_a_pii_redaction_policy(self) -> None:
        engine = PolicyEngine([_pii_policy("p1", "s", ["*"], ["ssn"])])
        assert engine.compile("s", "tool").has_response_side_policies is True

    def test_true_with_a_response_stage_custom_policy(self) -> None:
        engine = PolicyEngine([_custom_response_policy("c1", "s", ["*"], "x")])
        assert engine.compile("s", "tool").has_response_side_policies is True

    def test_false_with_only_a_request_stage_custom_policy(self) -> None:
        engine = PolicyEngine([_custom_request_policy("c1", "s", ["*"], "x")])
        assert engine.compile("s", "tool").has_response_side_policies is False
