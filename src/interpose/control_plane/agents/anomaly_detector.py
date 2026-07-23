"""Agent A2 -- Anomaly Detector (docs/INTERPOSE_SCOPING.md Section 7.8).

Two of the three detection strategies Section 7.8 describes are implemented:

1. **Rate-based** (z-score on 5-minute call-rate windows): computed against the
   *agent's own* recent history, live from the audit log -- there is no
   population-level historical baseline store (same gap noted for Agent A1). With
   fewer than 3 prior windows of history, a z-score isn't statistically meaningful,
   so this strategy is simply skipped (not faked with a default) until an agent has
   enough history.
2. **Rule-based**: one concrete pattern, "3+ denials for this agent in the last 15
   minutes" -- the one example pattern from Section 7.8 that's actually computable
   without AML-specific tooling. The doc's other examples ("5+ sanctions checks",
   "unusual tool for this agent role", "cross-session identity re-use") each need
   infrastructure that doesn't exist yet (a sanctions-check tool, an agent-role
   registry, cross-session identity correlation).

**Not implemented: cluster deviation** (K-means centroids trained by a Spark job).
That job doesn't exist -- it's Phase 3 analytics-plane work.

LLM usage is optional and exactly as narrow as Section 7.8 specifies: only when an
anomaly is flagged *and* its severity is `high`, producing one sentence. A failure to
generate that description (LLM down, invalid output) doesn't block the flag itself
from being raised -- the deterministic signal is what matters; the sentence is a
nice-to-have on top of it.
"""

from __future__ import annotations

import statistics
from collections.abc import Awaitable, Callable
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from interpose.audit.models import AuditEntry
from interpose.control_plane.llm import LLMError, generate_structured
from interpose.control_plane.state import AnomalyFlag, DecisionEvent, InterposeState

# Below this many prior 5-minute windows of history, a z-score isn't meaningful.
MIN_WINDOWS_FOR_ZSCORE = 3
ZSCORE_FLAG_THRESHOLD = 3.0
ZSCORE_HIGH_SEVERITY_THRESHOLD = 5.0
REPEATED_DENIALS_THRESHOLD = 3
REPEATED_DENIALS_HIGH_SEVERITY_THRESHOLD = 5


class AnomalySignals(BaseModel):
    current_window_calls: int
    prior_window_call_counts: list[int]
    denials_last_15_min: int


async def compute_anomaly_signals(
    session_factory: async_sessionmaker, event: DecisionEvent
) -> AnomalySignals:
    """Twelve 5-minute buckets covering the last hour for this agent: the most
    recent is "current," the rest are "prior" history for the z-score."""
    async with session_factory() as session:
        bucket_counts: list[int] = []
        for i in range(12):
            window_end = event.timestamp - timedelta(minutes=5 * i)
            window_start = window_end - timedelta(minutes=5)
            count = await session.scalar(
                select(func.count())
                .select_from(AuditEntry)
                .where(
                    AuditEntry.agent_id == event.agent_id,
                    AuditEntry.timestamp >= window_start,
                    AuditEntry.timestamp < window_end,
                )
            )
            bucket_counts.append(count or 0)

        denials_last_15_min = await session.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(
                AuditEntry.agent_id == event.agent_id,
                AuditEntry.status == "DENIED",
                AuditEntry.timestamp >= event.timestamp - timedelta(minutes=15),
            )
        )

    return AnomalySignals(
        current_window_calls=bucket_counts[0],
        prior_window_call_counts=bucket_counts[1:],
        denials_last_15_min=denials_last_15_min or 0,
    )


def compute_rate_zscore(signals: AnomalySignals) -> float | None:
    history = [c for c in signals.prior_window_call_counts if c is not None]
    if len(history) < MIN_WINDOWS_FOR_ZSCORE:
        return None
    mean = statistics.mean(history)
    stdev = statistics.stdev(history) if len(history) > 1 else 0.0
    if stdev == 0:
        return None
    return (signals.current_window_calls - mean) / stdev


def detect_anomaly(signals: AnomalySignals, event: DecisionEvent) -> AnomalyFlag | None:
    """Rate-based check runs first; a rate spike is the more specific, more
    actionable signal when both would otherwise fire in the same window."""
    zscore = compute_rate_zscore(signals)
    if zscore is not None and abs(zscore) > ZSCORE_FLAG_THRESHOLD:
        severity = "high" if abs(zscore) >= ZSCORE_HIGH_SEVERITY_THRESHOLD else "med"
        return AnomalyFlag(
            event=event,
            anomaly_type="rate_spike",
            severity=severity,
            evidence={
                "zscore": zscore,
                "current_window_calls": signals.current_window_calls,
                "prior_window_call_counts": signals.prior_window_call_counts,
            },
        )

    if signals.denials_last_15_min >= REPEATED_DENIALS_THRESHOLD:
        severity = (
            "high"
            if signals.denials_last_15_min >= REPEATED_DENIALS_HIGH_SEVERITY_THRESHOLD
            else "med"
        )
        return AnomalyFlag(
            event=event,
            anomaly_type="repeated_denials",
            severity=severity,
            evidence={"denials_last_15_min": signals.denials_last_15_min},
        )

    return None


class AnomalyDescription(BaseModel):
    description: str


async def _describe_high_severity_anomaly(
    flag: AnomalyFlag, generate_fn: Callable[..., Awaitable[BaseModel]]
) -> str | None:
    try:
        result = await generate_fn(
            system_prompt=(
                "You are a security analyst summarizing an anomalous MCP tool-call "
                "pattern in one plain-English sentence for a compliance reviewer."
            ),
            user_prompt=(
                f"Anomaly type: {flag.anomaly_type}\nEvidence: {flag.evidence}\n"
                f"Tool: {flag.event.tool}, server: {flag.event.server}."
            ),
            output_model=AnomalyDescription,
        )
        return result.description
    except LLMError:
        return None


NodeFn = Callable[[InterposeState], Awaitable[dict]]


def make_anomaly_detector_node(
    session_factory: async_sessionmaker,
    generate_fn: Callable[..., Awaitable[BaseModel]] = generate_structured,
) -> NodeFn:
    async def node(state: InterposeState) -> dict:
        signals = await compute_anomaly_signals(session_factory, state.event)
        flag = detect_anomaly(signals, state.event)
        if flag is None:
            return {}
        if flag.severity == "high":
            description = await _describe_high_severity_anomaly(flag, generate_fn)
            if description is not None:
                evidence = {**flag.evidence, "description": description}
                flag = flag.model_copy(update={"evidence": evidence})
        return {"anomaly": flag}

    return node
