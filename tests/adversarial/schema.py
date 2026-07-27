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
    """What the audit log should show after the scenario runs."""

    status: str
    policy_fired: str | None = None

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
