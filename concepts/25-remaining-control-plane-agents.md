# The remaining control-plane agents: A2, A3, A4

Follows [[22-langgraph-fundamentals-and-supervisor-routing]] and
[[24-narrative-generation-with-a-real-llm]]. Phase 2 Day 8;
`docs/INTERPOSE_SCOPING.md` Sections 7.8-7.10. All five control-plane agents are now
real.

## Agent A2 — Anomaly Detector: a live z-score, not a trained baseline

Section 7.8 describes three detection strategies. Two are implemented: a rate-based
z-score, and one rule-based pattern (3+ denials for an agent in 15 minutes — the one
example from the doc's list that doesn't need AML-specific tooling that doesn't exist
yet). The third, **cluster deviation against Spark-trained K-means centroids, is not
implemented** — that training job is Phase 3 analytics-plane work.

The z-score itself is computed *live* against the agent's own last hour of history
(twelve 5-minute buckets), not against a pre-trained population baseline — the same
"materialized view" gap already named for Agent A1 ([[23-control-plane-event-bus-and-feature-engineering]]).
Worth calling out explicitly: **with fewer than 3 prior windows of history, no
z-score is computed at all** — not a default of zero, not a guess. A brand-new agent
with two calls in its history genuinely doesn't have enough data for "unusual" to mean
anything yet, and pretending otherwise would produce a confident-looking number with
no statistical basis. Same reasoning for a zero-stdev history (every prior window
identical): dividing by zero isn't "no anomaly," it's undefined, so the function
returns `None` rather than crashing or lying.

## Agent A4 — Incident Escalator: a real graph-topology extension, and a severity bug

Of Section 7.10's four promotion rules, three are real: repeated denials (independent
of Agent A1 — this node is reachable via the direct `DENY` path, which skips A1
entirely, so it can't just read `state.enriched`), a high-severity anomaly flag, and
session risk above 0.8 with a pending HITL hold. The fourth (a `DENY` specifically on
a sanctions-check tool) isn't implemented; that tool doesn't exist before Phase 3.

**Adding A4 for real meant extending Day 7's graph, not just filling in a stub.** The
existing topology only reached the incident escalator via one path (direct `DENY`).
But Section 7.10 also promotes on a high-severity anomaly — which only Agent A2 can
raise, and A2 sat on a completely different branch of the graph, ending at `END` with
no path onward. `route_after_anomaly_detector` (added this day, in
`interpose.control_plane.agents.supervisor`) closes that gap: a high-severity flag now
continues on to A4, a low/absent one still ends there. The *fourth* rule (risk > 0.8
via a pending HITL) is still not reachable via the graph — that would need Agent A3
to conditionally continue onward instead of always ending, which isn't wired up. The
promotion **logic** (`should_promote`) already handles this case correctly regardless
of whether the graph can currently reach it; the gap is specifically in routing, named
here rather than silently left unreachable with no explanation.

**A real severity bug, caught by the integration tests, not a live LLM call this
time.** `should_promote` checks the repeated-denials rule before the anomaly-severity
rule — so a case that trips *both* (enough denials to promote on its own, alongside a
high-severity anomaly A2 already raised) reported "repeated_denials" as the matched
rule, and the original code assigned severity purely off which rule string came back:
`med`, silently under-reporting a genuinely high-severity situation. Fixed by
`compute_incident_severity`, a separate, directly-tested function: severity is `high`
if the matched rule is inherently severe, *or* if a high-severity anomaly is present
at all — independent of which rule happened to be checked first. This is exactly the
kind of bug end-to-end tests exist to catch: each piece (the rule-matching order, the
severity assignment) looked correct in isolation.

## Agent A3 — Evidence Composer: what "similar patterns" actually means here

Section 7.9 wants "prior HITL decisions by same reviewer group on similar patterns."
Genuine pattern-similarity matching — clustering past decisions by how alike their
circumstances were — is out of scope for an MVP; what's built instead is a much
simpler, honestly-named proxy: a count of prior `APPROVED`/`DENIED` decisions for this
*same agent, same tool* combination, queried directly from the audit log. Not
"similar," just "the same thing before" — a real, useful signal for a reviewer
("this agent has been denied this exact tool 3 times already"), just a narrower one
than the doc's phrasing implies.

A3 is the one agent guaranteed to have `state.enriched` populated no matter how it's
reached, because Section 7.6's routing sends `HOLD` through Agent A1 before A3, never
around it — unlike A4, A3's node can rely on `state.enriched` without an independent
query, and does (with a loud `RuntimeError` if that invariant is ever violated, rather
than silently composing a packet with missing risk context).

## Related

- [[24-narrative-generation-with-a-real-llm]]
- [[22-langgraph-fundamentals-and-supervisor-routing]]
- [[23-control-plane-event-bus-and-feature-engineering]]
