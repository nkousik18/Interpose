"""Registry of the 6 attack classes required by G9 (docs/INTERPOSE_SCOPING.md
Section 4.2 / 10.5 / 13.5). Independent of whether a fixture template exists for a
class yet -- see generate.py and README.md for what's real today vs. Phase 4 scope.
"""

from dataclasses import dataclass
from enum import StrEnum


class AttackClass(StrEnum):
    PROMPT_INJECTION_VIA_TOOL_OUTPUT = "prompt_injection_via_tool_output"
    DATA_EXFILTRATION = "data_exfiltration"
    UNAUTHORIZED_WRITE = "unauthorized_write"
    OVER_PERMISSIONED_TOOL_ACCESS = "over_permissioned_tool_access"
    CREDENTIAL_LEAKAGE = "credential_leakage"
    CHAINED_TOOL_PRIVILEGE_ESCALATION = "chained_tool_privilege_escalation"


@dataclass(frozen=True)
class AttackClassInfo:
    defense_mechanism: str
    # What's missing before a *real* fixture can be written for this class -- "a
    # scripted fixture" for classes where the enforcement already exists, or a
    # concrete gateway capability for classes where it doesn't yet.
    capability_needed: str


ATTACK_CLASS_REGISTRY: dict[AttackClass, AttackClassInfo] = {
    AttackClass.PROMPT_INJECTION_VIA_TOOL_OUTPUT: AttackClassInfo(
        defense_mechanism="Response-side (Hook 2) policy scan, quarantine for HITL",
        capability_needed=(
            "a response-side policy hook -- only the pre-forward hook (Hook 1, "
            "Stages 4-5) is wired into the gateway today"
        ),
    ),
    AttackClass.DATA_EXFILTRATION: AttackClassInfo(
        defense_mechanism="rate_limit / denylist policy + Agent A2 anomaly detection",
        capability_needed="a scripted fixture -- rate_limit policies and Agent A2 already exist",
    ),
    AttackClass.UNAUTHORIZED_WRITE: AttackClassInfo(
        defense_mechanism="hitl_gate policy holds any write without prior approval",
        capability_needed="a scripted fixture -- hitl_gate policies already exist",
    ),
    AttackClass.OVER_PERMISSIONED_TOOL_ACCESS: AttackClassInfo(
        defense_mechanism="allowlist policy denies at tools/call",
        capability_needed="a scripted fixture -- allowlist policies already exist",
    ),
    AttackClass.CREDENTIAL_LEAKAGE: AttackClassInfo(
        defense_mechanism="pii_redaction policy redacts and audits",
        capability_needed=(
            "a real pii_redaction implementation -- today it's a schema stub "
            "(interpose.policies.schema) that raises NotImplementedError if evaluated"
        ),
    ),
    AttackClass.CHAINED_TOOL_PRIVILEGE_ESCALATION: AttackClassInfo(
        defense_mechanism=(
            "Agent A2 anomaly detector + Agent A4 incident escalator promote the pattern"
        ),
        capability_needed="a scripted fixture -- Agents A2/A4 already exist",
    ),
}
