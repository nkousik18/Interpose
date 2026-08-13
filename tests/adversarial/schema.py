"""Pydantic schema for one adversarial test scenario (docs/INTERPOSE_SCOPING.md
Section 10.5): a scripted sequence of `tools/call` requests plus the outcome
Interpose is expected to produce, checked against the real audit log after the
scenario runs -- not against gateway internals.
"""

from pydantic import BaseModel, Field, field_validator

from interpose.audit.models import STATUSES

from .attack_classes import AttackClass


class ToolCallStep(BaseModel):
    """One `tools/call` request in the scripted attack sequence."""

    server: str
    tool: str
    args: dict[str, object] = Field(default_factory=dict)


class ExpectedOutcome(BaseModel):
    """What the audit log (and, for a couple of classes, the real MCP response or
    the control-plane's own persisted tables -- Phase 3's gap-closing work) should
    show after the scenario's *last* scripted call runs. Earlier calls in a
    multi-call scenario (e.g. `data_exfiltration`'s first, under-the-limit call) are
    setup, asserted implicitly by the last call actually producing the outcome it's
    supposed to -- not separately checked call-by-call; a scenario needing that
    would be reaching for something this schema doesn't try to be.

    Every field beyond `status`/`policy_fired` defaults to "don't check this" (empty
    list / None / False) -- most attack classes only need the two original fields;
    the rest exist because `status`/`policy_fired` alone can't express what actually
    proves the defense fired for a few specific classes (see each field's docstring).
    """

    status: str
    policy_fired: str | None = None
    # `credential_leakage`: audit status/policy_fired alone can't prove redaction
    # actually happened to the response content -- pii_redaction contributes no
    # tag and isn't the request-side `fired_policy` (it's Stage 8, after the
    # PASS/DENY/HOLD decision is already made). The harness checks these against
    # the real MCP response the scripted call actually received.
    response_contains: str | None = None
    response_not_contains: str | None = None
    # `prompt_injection_via_tool_output`: the response-side custom policy that
    # detects it tags the audit entry but changes neither `status` nor
    # `policy_fired` (interpose.policies.packs.demo's docstring explains why it
    # can't). This is the only way to prove detection actually fired.
    tags_include: list[str] = Field(default_factory=list)
    # `chained_tool_privilege_escalation`: the real outcome lives in the `incidents`
    # table (Phase 3's control-plane persistence work), not `audit_entries` at all --
    # Agent A4 processes the scripted denials asynchronously, off the gateway's hot
    # path, well after the scripted calls themselves return.
    incident_expected: bool = False

    @field_validator("status")
    @classmethod
    def _status_is_real(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError(f"{value!r} is not a real audit status; must be one of {STATUSES}")
        return value


class AdversarialScenario(BaseModel):
    id: str
    attack_class: AttackClass
    description: str
    calls: list[ToolCallStep]
    expected: ExpectedOutcome
