"""Pydantic policy models -- the typed shape of a policy YAML file
(docs/INTERPOSE_SCOPING.md Section 6.6). All five effect types
(allowlist, denylist, rate_limit, pii_redaction, hitl_gate) parse as of
docs/ROADMAP.md Phase 1 Day 3, but only the first three are actually enforced by
`interpose.policies.policyset.PolicySet.evaluate` -- a policy pack that includes a
`pii_redaction` or `hitl_gate` effect will load and validate fine, but evaluating it
raises `NotImplementedError` rather than silently letting the call through
unprotected. Real enforcement lands in a later phase.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Fixed evaluation order per Section 6.5 Stage 5. A PolicySet's policies are grouped by
# this order, then by declaration order within a group. Only the first three exist yet.
EFFECT_ORDER: tuple[str, ...] = (
    "allowlist",
    "denylist",
    "rate_limit",
    "pii_redaction",
    "hitl_gate",
    "custom",
)


class AppliesTo(BaseModel):
    """Which {server, tool} pairs a policy governs. "*" in tools matches any tool."""

    server: str
    tools: list[str]

    def matches(self, server: str, tool: str) -> bool:
        return self.server == server and ("*" in self.tools or tool in self.tools)


class AllowlistEffect(BaseModel):
    type: Literal["allowlist"] = "allowlist"


class DenylistEffect(BaseModel):
    type: Literal["denylist"] = "denylist"
    reason: str = "denylisted"


class RateLimitEffect(BaseModel):
    type: Literal["rate_limit"] = "rate_limit"
    limit: int = Field(gt=0)
    window_seconds: int = Field(gt=0)


class PiiRedactionEffect(BaseModel):
    """Schema stub (Day 3) -- not yet enforced. Field shape matches Stage 5's
    REDACT(replacements) outcome: which named PII patterns to redact from arguments
    and/or the response payload."""

    type: Literal["pii_redaction"] = "pii_redaction"
    patterns: list[str] = Field(default_factory=list)


class HitlGateEffect(BaseModel):
    """Schema stub (Day 3) -- not yet enforced. Fields match the Section 6.6 example."""

    type: Literal["hitl_gate"] = "hitl_gate"
    reviewer_group: str
    timeout_seconds: int = Field(gt=0)


Effect = Annotated[
    AllowlistEffect | DenylistEffect | RateLimitEffect | PiiRedactionEffect | HitlGateEffect,
    Field(discriminator="type"),
]


class AuditMeta(BaseModel):
    severity: Literal["low", "medium", "high"] = "low"
    tag: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    """One compiled unit of the policy DSL -- one YAML file, one Policy."""

    policy: str
    description: str = ""
    applies_to: AppliesTo
    effect: Effect
    audit: AuditMeta = Field(default_factory=AuditMeta)
