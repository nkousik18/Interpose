"""Custom policy hooks for the `hello-echo` demo pack (`config/policies/`) --
`hello-echo-prompt-injection-scan`, the response-side detection Phase 4's adversarial
suite exercises for the `prompt_injection_via_tool_output` attack class
(`tests/adversarial/`). Same module shape as `interpose.policies.packs.aml`.
"""

from __future__ import annotations

import logging
import re

from interpose.policies.custom import ResponsePolicyContext, register_response_policy
from interpose.policies.schema import Policy

logger = logging.getLogger(__name__)

# A small, illustrative set of phrases an injected instruction embedded in tool
# output is likely to contain -- not a claim of comprehensive prompt-injection
# detection (that's a genuinely hard, open problem), just enough to prove the
# detect-and-tag mechanism fires on a realistic-shaped attack. Case-insensitive,
# matched against the response's raw text content.
INJECTION_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (all|any|previous|prior) instructions", re.IGNORECASE),
    re.compile(r"disregard (the )?(system prompt|previous instructions)", re.IGNORECASE),
    re.compile(r"new instructions\s*:", re.IGNORECASE),
    re.compile(r"you are now\b", re.IGNORECASE),
)


def _contains_injection_marker(value: object) -> bool:
    """Walks an arbitrary parsed-JSON value the same way `redaction.redact_json_value`
    does, checking every string leaf against `INJECTION_MARKERS` -- deliberately
    generic rather than schema-aware, matching that module's own reasoning."""
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in INJECTION_MARKERS)
    if isinstance(value, list):
        return any(_contains_injection_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_injection_marker(item) for item in value.values())
    return False


@register_response_policy("hello_echo_prompt_injection_scan")
async def hello_echo_prompt_injection_scan(
    policy: Policy, ctx: ResponsePolicyContext
) -> list[str]:
    """Detects, tags -- does **not** block. `interpose.policies.custom`'s own
    documented design boundary: a response-side custom policy can never deny a call
    that's already completed (same reasoning `aml_structuring_alert` -- the AML
    pack's own response-side detection policy -- already established: this stage
    exists to flag and record, not to intercept). The tainted response still reaches
    the caller unmodified; `tests/adversarial/`'s scenario for this attack class
    asserts exactly that (COMPLETED, this tag present), not that the call was
    blocked -- an honest, named limitation, not a claim this project can't back up.
    """
    if not _contains_injection_marker(ctx.response_payload):
        return []
    logger.warning(
        "policy.hello_echo_prompt_injection_scan.fired session_id=%s tool=%s",
        ctx.session_id,
        ctx.tool,
    )
    return ["prompt-injection-detected"]
