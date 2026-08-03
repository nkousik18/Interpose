"""Unit tests for interpose.policies.schema -- the policy DSL's typed shape."""

import pytest
from pydantic import ValidationError

from interpose.policies.schema import (
    AllowlistEffect,
    AppliesTo,
    AuditMeta,
    CostCapEffect,
    CustomEffect,
    DenylistEffect,
    HitlGateEffect,
    PackManifest,
    PiiRedactionEffect,
    Policy,
    RateLimitEffect,
    TagOnlyEffect,
)


class TestAppliesTo:
    def test_matches_exact_tool(self) -> None:
        applies_to = AppliesTo(server="ofac-sanctions", tools=["check_name"])
        assert applies_to.matches("ofac-sanctions", "check_name")

    def test_matches_wildcard_tool(self) -> None:
        applies_to = AppliesTo(server="ofac-sanctions", tools=["*"])
        assert applies_to.matches("ofac-sanctions", "anything")

    def test_rejects_wrong_server(self) -> None:
        applies_to = AppliesTo(server="ofac-sanctions", tools=["*"])
        assert not applies_to.matches("transaction-graph", "anything")

    def test_rejects_unlisted_tool(self) -> None:
        applies_to = AppliesTo(server="ofac-sanctions", tools=["check_name"])
        assert not applies_to.matches("ofac-sanctions", "check_alias")

    def test_wildcard_server_matches_any_server(self) -> None:
        applies_to = AppliesTo(server="*", tools=["*"])
        assert applies_to.matches("ofac-sanctions", "anything")
        assert applies_to.matches("transaction-graph", "anything_else")


class TestEffects:
    def test_allowlist_effect_type_defaults(self) -> None:
        assert AllowlistEffect().type == "allowlist"

    def test_denylist_effect_default_reason(self) -> None:
        assert DenylistEffect().reason == "denylisted"

    def test_denylist_effect_custom_reason(self) -> None:
        assert DenylistEffect(reason="too risky").reason == "too risky"

    def test_rate_limit_effect_fields(self) -> None:
        effect = RateLimitEffect(limit=10, window_seconds=60)
        assert effect.limit == 10
        assert effect.window_seconds == 60

    def test_rate_limit_rejects_nonpositive_limit(self) -> None:
        with pytest.raises(ValidationError):
            RateLimitEffect(limit=0, window_seconds=60)

    def test_rate_limit_rejects_nonpositive_window(self) -> None:
        with pytest.raises(ValidationError):
            RateLimitEffect(limit=10, window_seconds=0)

    def test_pii_redaction_effect_defaults(self) -> None:
        assert PiiRedactionEffect().patterns == []

    def test_pii_redaction_effect_custom_patterns(self) -> None:
        assert PiiRedactionEffect(patterns=["email", "ssn"]).patterns == ["email", "ssn"]

    def test_hitl_gate_effect_fields(self) -> None:
        effect = HitlGateEffect(reviewer_group="aml-analysts", timeout_seconds=3600)
        assert effect.reviewer_group == "aml-analysts"
        assert effect.timeout_seconds == 3600

    def test_hitl_gate_requires_reviewer_group(self) -> None:
        with pytest.raises(ValidationError):
            HitlGateEffect(timeout_seconds=3600)

    def test_hitl_gate_rejects_nonpositive_timeout(self) -> None:
        with pytest.raises(ValidationError):
            HitlGateEffect(reviewer_group="aml-analysts", timeout_seconds=0)

    def test_custom_effect_defaults_to_request_stage_and_empty_params(self) -> None:
        effect = CustomEffect(name="aml_sanctions_required")
        assert effect.stage == "request"
        assert effect.params == {}

    def test_custom_effect_response_stage(self) -> None:
        effect = CustomEffect(name="aml_structuring_alert", stage="response")
        assert effect.stage == "response"

    def test_custom_effect_rejects_unknown_stage(self) -> None:
        with pytest.raises(ValidationError):
            CustomEffect(name="x", stage="somewhere_else")

    def test_tag_only_effect_type(self) -> None:
        assert TagOnlyEffect().type == "tag_only"

    def test_cost_cap_effect_fields(self) -> None:
        effect = CostCapEffect(session_limit_usd=2.0)
        assert effect.session_limit_usd == 2.0
        assert effect.warn_at_ratio == 0.8

    def test_cost_cap_rejects_nonpositive_limit(self) -> None:
        with pytest.raises(ValidationError):
            CostCapEffect(session_limit_usd=0)

    def test_cost_cap_rejects_warn_ratio_above_one(self) -> None:
        with pytest.raises(ValidationError):
            CostCapEffect(session_limit_usd=2.0, warn_at_ratio=1.5)


class TestAuditMeta:
    def test_defaults(self) -> None:
        meta = AuditMeta()
        assert meta.severity == "low"
        assert meta.tag == []

    def test_custom_values(self) -> None:
        meta = AuditMeta(severity="high", tag=["aml", "write"])
        assert meta.severity == "high"
        assert meta.tag == ["aml", "write"]

    def test_rejects_unknown_severity(self) -> None:
        with pytest.raises(ValidationError):
            AuditMeta(severity="extreme")


class TestPolicy:
    def test_parses_allowlist_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "read-only-allowlist",
                "applies_to": {"server": "ofac-sanctions", "tools": ["check_name"]},
                "effect": {"type": "allowlist"},
            }
        )
        assert isinstance(policy.effect, AllowlistEffect)
        assert policy.description == ""

    def test_parses_denylist_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "no-deletes",
                "applies_to": {"server": "transaction-graph", "tools": ["delete_record"]},
                "effect": {"type": "denylist", "reason": "irreversible"},
            }
        )
        assert isinstance(policy.effect, DenylistEffect)
        assert policy.effect.reason == "irreversible"

    def test_parses_rate_limit_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "throttle-checks",
                "applies_to": {"server": "ofac-sanctions", "tools": ["*"]},
                "effect": {"type": "rate_limit", "limit": 100, "window_seconds": 60},
            }
        )
        assert isinstance(policy.effect, RateLimitEffect)
        assert policy.effect.limit == 100

    def test_parses_hitl_gate_policy(self) -> None:
        """Matches the Section 6.6 YAML example verbatim (as a dict)."""
        policy = Policy.model_validate(
            {
                "policy": "aml-write-hitl-gate",
                "description": "All write actions on the transaction-graph server require HITL.",
                "applies_to": {
                    "server": "transaction-graph",
                    "tools": ["write_annotation", "mark_investigated"],
                },
                "effect": {
                    "type": "hitl_gate",
                    "reviewer_group": "aml-analysts",
                    "timeout_seconds": 3600,
                },
                "audit": {"severity": "high", "tag": ["aml", "write", "hitl"]},
            }
        )
        assert isinstance(policy.effect, HitlGateEffect)
        assert policy.effect.reviewer_group == "aml-analysts"
        assert policy.audit.tag == ["aml", "write", "hitl"]

    def test_rejects_unknown_effect_type(self) -> None:
        with pytest.raises(ValidationError):
            Policy.model_validate(
                {
                    "policy": "bad-policy",
                    "applies_to": {"server": "x", "tools": ["*"]},
                    "effect": {"type": "not_a_real_type"},
                }
            )

    def test_requires_effect(self) -> None:
        with pytest.raises(ValidationError):
            Policy.model_validate(
                {"policy": "no-effect", "applies_to": {"server": "x", "tools": ["*"]}}
            )

    def test_parses_custom_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "aml-sanctions-required",
                "applies_to": {"server": "transaction-graph", "tools": ["*"]},
                "effect": {"type": "custom", "name": "aml_sanctions_required"},
            }
        )
        assert isinstance(policy.effect, CustomEffect)
        assert policy.effect.stage == "request"

    def test_parses_tag_only_policy(self) -> None:
        policy = Policy.model_validate(
            {
                "policy": "aml-audit-tagging",
                "applies_to": {"server": "*", "tools": ["*"]},
                "effect": {"type": "tag_only"},
                "audit": {"tag": ["pack:aml", "regulation:BSA"]},
            }
        )
        assert isinstance(policy.effect, TagOnlyEffect)
        assert policy.audit.tag == ["pack:aml", "regulation:BSA"]


class TestPackManifest:
    def test_parses_a_manifest(self) -> None:
        manifest = PackManifest.model_validate(
            {
                "name": "aml",
                "version": "0.1.0",
                "description": "FinCEN/BSA-aligned policy pack.",
                "maintainer": "Kousik",
                "regulation_references": ["BSA (31 U.S.C. 5311 et seq.)"],
                "tags": ["aml", "bsa"],
                "policies": ["aml-sanctions-required", "aml-write-hitl-gate"],
            }
        )
        assert manifest.name == "aml"
        assert manifest.policies == ["aml-sanctions-required", "aml-write-hitl-gate"]

    def test_requires_policies_list(self) -> None:
        with pytest.raises(ValidationError):
            PackManifest.model_validate({"name": "aml", "version": "0.1.0"})
