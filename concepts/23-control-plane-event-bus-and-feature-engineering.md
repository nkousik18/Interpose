# The control plane's event bus, and Agent A1's feature engineering

Follows [[22-langgraph-fundamentals-and-supervisor-routing]] (the graph itself).
Phase 2 Day 7; `docs/INTERPOSE_SCOPING.md` Section 6.9, 7.7, 7.12.

## Decoupling the control plane from the gateway's hot path

Every governed tool call already does real work on the request path: policy
evaluation, a hash-chained audit write, possibly a HITL hold
([[21-redis-and-the-hitl-hold]]). None of that should get slower because a LangGraph
agent also wants to look at the event — Section 7.12 states this outright: "Control
plane is async from the hot path."

The mechanism is about as simple as it can be:
`interpose.control_plane.bus.EventBus` wraps a plain `asyncio.Queue`. The gateway's
`_publish_decision_event` does `await queue.put(event)` right after each
decision-defining audit write (`DENIED`, `HELD`, or `INTENT` — never the
`COMPLETED`/`UPSTREAM_ERROR` follow-ups, since those don't represent a *new* decision,
just the outcome of one already published). Putting something on an unbounded
`asyncio.Queue` returns essentially instantly — the gateway's response to the agent
doesn't wait on anything the control plane does with that event afterward.

A single background `asyncio.Task` (`interpose.control_plane.runner.run_forever`,
started at gateway startup, cancelled at shutdown) pulls events off the queue one at a
time and runs each through the compiled graph. If graph execution throws — a bug in an
agent, a database hiccup — it's logged and the loop keeps going; a control-plane
failure must never retroactively change a decision that already happened and was
already audited before the event was even published.

**Why this is "the documented seam," not just an implementation detail.** Section
6.17 names `interpose.control_plane.bus.EventBus` specifically as the interface to
swap when this needs to scale beyond one process (Redis Streams, for multiple gateway
replicas feeding one shared control plane). Nothing about `publish`/`consume`'s
signatures needs to change for that swap — only what's inside the class.

## Agent A1's features: computed live, not from a materialized view

Section 7.7 describes A1's inputs as including "historical baseline features from
Postgres (materialized view refreshed every 15 minutes)." That view doesn't exist —
building one is real Spark/analytics-plane work (the same kind of job
[[14-spark-and-pyspark]] introduced), disproportionate to what's actually needed at
current data volumes. `compute_context_features` just queries `audit_entries`
directly for the session's own rows. Simpler, and entirely sufficient today; worth
revisiting only once a live query actually becomes too slow to run per-event.

**Three named features are deliberately not computed**, each missing a specific,
nameable dependency rather than just being unfinished:
- **Read/write ratio** — would need a registry classifying each tool as a read or
  write action. Nothing currently declares that; policies match by tool *name*, not
  by a declared action type.
- **Sanctions-check frequency** — an AML-specific signal referencing a tool
  (`check_name` on the OFAC sanctions server) that doesn't exist before Phase 3.
- **Per-tool baseline z-scores** — needs the same historical-baseline store as the
  materialized view above.

What's computed instead — calls in the last minute, unique tools touched, total calls,
HITL ticket count, denial count, all scoped to the current session — is real,
queryable today, and enough to give the Supervisor's second routing hop something
genuine to act on.

## The risk score is a heuristic, not a model

`compute_session_risk_score` is a hand-weighted sum of those features, clipped to
`[0, 1]`. It is explicitly **not** a calibrated statistical model — there's no
production traffic yet to calibrate weights against, and Section 7.8's actual
anomaly-detection approach (Agent A2, Day 8: z-scores, rule-based patterns, K-means
cluster deviation from a Spark-trained model) is the principled version of "is this
unusual," built for a different, more specific purpose. A1's score exists only to give
`RISK_THRESHOLD`-based routing *something* real to compare against; both the formula
and the threshold (`0.5`) are placeholders pending real data, and are written down as
such in the code, not left to look more authoritative than they are.

## A real (if partial) implementation of the deferred session-state hash

Section 6.8 describes an `interpose:session:{agent_id}` Redis hash for session
metadata — deferred twice already (Day 5, Day 6) because nothing read or wrote it.
Agent A1 now does: after computing a risk score, it writes `risk_score`,
`last_updated`, and `agent_id` into `interpose:session:{session_id}` (keyed by session,
which is what the audit trail actually keys on). This is deliberately the smallest
real slice of Section 6.8's full design — no active-HITL-ticket list, no separately
tracked "start time" — built because it was the natural, honestly-useful side effect
to hang the "decisions really do flow from the gateway to the control plane" test on
(`tests/integration/test_gateway_control_plane.py` polls exactly this key), not
because the whole session-state design suddenly became needed at once.

## Related

- [[22-langgraph-fundamentals-and-supervisor-routing]]
- [[21-redis-and-the-hitl-hold]]
- [[14-spark-and-pyspark]]
