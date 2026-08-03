"""Pydantic policy models -- the typed shape of a policy YAML file
(docs/INTERPOSE_SCOPING.md Section 6.6). Eight effect types as of Phase 3 Day 14
(allowlist, denylist, rate_limit, pii_redaction, hitl_gate, custom, tag_only,
cost_cap):

- `allowlist`/`denylist`/`rate_limit`/`hitl_gate` -- request-side (Stage 5), evaluated
  before forwarding, unchanged since Phase 1-2.
- `pii_redaction` -- response-side (Stage 8) as of today. It parsed but was never
  enforced from Phase 1 Day 3 through Phase 3 Day 13 (evaluating it raised
  `NotImplementedError`); real enforcement needed the gateway to actually buffer and
  parse tool responses, which it didn't do until today (see
  `interpose.gateway.app._forward_and_record`).
- `custom` -- request-side *or* response-side (its own `stage` field says which),
  dispatching by `name` to a small registered-function plugin
  (`interpose.policies.custom`) rather than letting policy YAML embed arbitrary code --
  a deliberate security boundary, not just a convenience choice.
- `tag_only` -- new today, for policies like `aml-audit-tagging` that exist purely to
  attach `audit.tag` values to every matching call's audit entry, with no gating
  behavior of their own.
- `cost_cap` -- schema stub, same status `pii_redaction` had for 10 days: parses, but
  evaluating it raises `NotImplementedError` (see `CostCapEffect`'s docstring for why).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Fixed evaluation order per Section 6.5 Stage 5. A PolicySet's policies are grouped by
# this order, then by declaration order within a group -- used for compile-time
# sorting/display; actual request-side precedence is hardcoded in
# PolicySet.evaluate's fixed sequence of checks, not derived from this tuple.
EFFECT_ORDER: tuple[str, ...] = (
    "tag_only",
    "allowlist",
    "denylist",
    "rate_limit",
    "custom",
    "hitl_gate",
    "cost_cap",
    "pii_redaction",
)


class AppliesTo(BaseModel):
    """Which {server, tool} pairs a policy governs. "*" in tools matches any tool;
    "*" as the server matches every server -- added Phase 3 Day 14 for cross-cutting
    policies like `aml-audit-tagging` that aren't specific to one upstream server."""

    server: str
    tools: list[str]

    def matches(self, server: str, tool: str) -> bool:
        server_matches = self.server == "*" or self.server == server
        return server_matches and ("*" in self.tools or tool in self.tools)


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
    """Response-side (Stage 8) as of Phase 3 Day 14 -- `patterns` names entries in
    `interpose.policies.redaction.PII_PATTERNS` (e.g. "ssn", "credit_card",
    "bank_account"), applied to the tool's response content before it reaches the
    calling agent. Never touches request arguments -- Section 9.8's P3 only asks to
    redact response payloads, and every response this project's MCP servers actually
    produce is where the risk of leaking a raw account number back to the agent's own
    context actually lives."""

    type: Literal["pii_redaction"] = "pii_redaction"
    patterns: list[str] = Field(default_factory=list)


class HitlGateEffect(BaseModel):
    """Request-side (Stage 5), real since Phase 2 Day 6. Fields match the Section 6.6
    example."""

    type: Literal["hitl_gate"] = "hitl_gate"
    reviewer_group: str
    timeout_seconds: int = Field(gt=0)


class CustomEffect(BaseModel):
    """Dispatches by `name` to a registered Python function
    (`interpose.policies.custom`) rather than letting policy YAML embed arbitrary
    code -- a security boundary: a policy pack is data a deployer can drop into
    `config/policies`, and data that can execute arbitrary code is a code-injection
    vector, not a policy. `stage` says which lifecycle point the engine dispatches it
    at: "request" (Stage 5, before forwarding -- can DENY, like `aml-sanctions-required`)
    or "response" (Stage 8, after the upstream response is available -- can tag the
    audit entry and cause side effects, but never denies a call that already
    completed, like `aml-structuring-alert`)."""

    type: Literal["custom"] = "custom"
    name: str
    stage: Literal["request", "response"] = "request"
    params: dict = Field(default_factory=dict)


class TagOnlyEffect(BaseModel):
    """No gating behavior at all -- exists purely so a policy's `audit.tag` values
    get attached to every audit entry for the {server, tool} pairs it applies to
    (e.g. `aml-audit-tagging`'s `server: "*"` tagging every AML-pack call with
    `pack:aml`, `regulation:BSA`). Always contributes to `PolicySet.audit_tags`;
    never affects the PASS/DENY/HOLD outcome."""

    type: Literal["tag_only"] = "tag_only"


class CostCapEffect(BaseModel):
    """Schema stub (Phase 3 Day 14) -- parses and validates, but
    `PolicySet.evaluate` raises `NotImplementedError` if one shows up in an
    applicable PolicySet, same as `pii_redaction`/`hitl_gate` were from Day 3 until
    their own real enforcement landed. Not implemented because there's nothing real
    to enforce yet: the gateway has no visibility into LLM token cost at all -- an
    agent's LLM calls (like `agents/aml-investigator`'s Assessment/Report nodes)
    happen out-of-process, never through Interpose. `session_limit_usd` and
    `warn_at_ratio` match Section 9.8's P7 field shape so a real implementation (were
    the gateway ever given a way to observe that spend) wouldn't need a schema
    change, just an evaluator."""

    type: Literal["cost_cap"] = "cost_cap"
    session_limit_usd: float = Field(gt=0)
    warn_at_ratio: float = Field(default=0.8, gt=0, le=1.0)


Effect = Annotated[
    AllowlistEffect
    | DenylistEffect
    | RateLimitEffect
    | PiiRedactionEffect
    | HitlGateEffect
    | CustomEffect
    | TagOnlyEffect
    | CostCapEffect,
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


class PackManifest(BaseModel):
    """The typed shape of a policy pack's `pack.yaml` (Section 9.8) -- separate from
    `Policy` itself; `interpose.policies.loader.load_policy_pack` skips `pack.yaml`
    when globbing `*.yaml` for policies, and cross-validates that `policies` here
    names exactly the policy files actually present in the directory (Phase 3
    Day 14) -- a pack manifest that silently drifts from its own directory is worse
    than no manifest at all."""

    name: str
    version: str
    description: str = ""
    maintainer: str = ""
    regulation_references: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    policies: list[str]
