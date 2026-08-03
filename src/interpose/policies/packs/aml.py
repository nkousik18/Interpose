"""Custom policy hooks for the AML pack (docs/INTERPOSE_SCOPING.md Section 9.8,
Phase 3 Day 14): `aml-sanctions-required` (request-side) and `aml-structuring-alert`
(response-side). The declarative YAML lives in `policies/packs/aml/`; this module is
what those two policies' `custom` effects actually run.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from interpose.audit.models import AuditEntry
from interpose.policies.custom import (
    RequestPolicyContext,
    ResponsePolicyContext,
    register_request_policy,
    register_response_policy,
)
from interpose.policies.schema import Policy

logger = logging.getLogger(__name__)

# Which OFAC tools count as "a sanctions check happened" for aml-sanctions-required.
SANCTIONS_CHECK_TOOLS = ("check_entity", "check_alias")

# How long a structuring-alert's session flag persists in Redis. Generous on purpose:
# this is a signal for whoever reads it later (a reviewer, a future policy), not a
# lock that needs to expire quickly.
FORCE_HITL_TTL_SECONDS = 24 * 60 * 60


@register_request_policy("aml_sanctions_required")
async def aml_sanctions_required(policy: Policy, ctx: RequestPolicyContext) -> str | None:
    """P1: before any transaction-graph tool call, this *agent* must already have a
    COMPLETED OFAC check_entity/check_alias call somewhere in its history.

    Correlated on `agent_id`, not `session_id` -- see `RequestPolicyContext`'s
    docstring for why `session_id` (the MCP transport's `Mcp-Session-Id`) can't work
    across two different upstream servers at all, confirmed live before this was
    written this way. `agents/aml-investigator`'s `InvestigationClient` sends a
    consistent `Authorization` bearer token across both its OFAC and
    transaction-graph connections specifically so this correlation is possible.

    Also deliberately agent-level, not per-account, despite Section 9.8's "a prior
    sanctions check *on that account*" wording: `check_entity`/`check_alias` take a
    free-text `name`, never the transaction-graph server's `account_id` -- there is
    no shared key to match "this specific account was checked" against "this specific
    account is being queried" across the two servers' actual tool schemas. An
    agent-level requirement is the honest, implementable reading: some sanctions
    check happened first, not a false promise of per-account traceability the tools
    themselves can't back up.
    """
    async with ctx.session_factory() as session:
        found = await session.scalar(
            select(AuditEntry.id)
            .where(
                AuditEntry.agent_id == ctx.agent_id,
                AuditEntry.server == "ofac-sanctions",
                AuditEntry.tool.in_(SANCTIONS_CHECK_TOOLS),
                AuditEntry.status == "COMPLETED",
            )
            .limit(1)
        )
    if found is None:
        return (
            "no prior OFAC sanctions check (check_entity/check_alias) found for this "
            "agent before a transaction-graph call"
        )
    return None


@register_response_policy("aml_structuring_alert")
async def aml_structuring_alert(policy: Policy, ctx: ResponsePolicyContext) -> list[str]:
    """P5: fires when `structuring_check`'s response has `flagged=true`.

    Section 9.8 describes this triggering on "signal_strength > 0.7" -- no such field
    exists on the real `StructuringSignal` response
    (mcp-servers/transaction-graph/src/graph_models.py); the server only ever returns
    a boolean `flagged`. Using the field that actually exists rather than the
    doc's invented one, same correction this project has made for every other
    scoping-doc-vs-reality mismatch.

    Effect, scoped to what's real: tags this audit entry as a high-severity incident,
    and sets a session-scoped Redis flag recording that a structuring signature was
    seen. Section 9.8 additionally says this should "require the next mutating action
    in the session to go through HITL regardless of other policies" -- in this pack
    specifically, that's already unconditionally true: `aml-write-hitl-gate` (P2)
    HITL-gates every write on transaction-graph (the only mutating tool that exists,
    `mark_investigated`) with no condition to override. Building a second enforcement
    path to read this flag back would be enforcing something already guaranteed by a
    different policy -- dead code with nothing to override, not a missing feature.
    The flag is still set for real, so it's available to a reviewer or a future,
    weaker write policy that doesn't already cover every write unconditionally.
    """
    if not isinstance(ctx.response_payload, dict) or not ctx.response_payload.get("flagged"):
        return []

    flag_key = f"interpose:session:{ctx.session_id}:force_hitl"
    await ctx.redis.set(flag_key, "aml_structuring_alert", ex=FORCE_HITL_TTL_SECONDS)
    logger.info(
        "policy.aml_structuring_alert.fired session_id=%s account_id=%s",
        ctx.session_id,
        ctx.arguments.get("account_id"),
    )
    return ["incident:structuring", "severity:high"]
