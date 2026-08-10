# Persisting control-plane decisions: from ephemeral state to queryable history

Follows [[22-langgraph-fundamentals-and-supervisor-routing]] and
[[25-remaining-control-plane-agents]]. Closes a named gap left open by Phase 3 Day 15
(`docs/project/SESSION_LOG.md`): Agent A2's anomaly flags, Agent A4's incident
promotions, and Agent A1's session risk score were all computed for real, then thrown
away the moment a graph run finished.

## Why they were ephemeral in the first place

`InterposeState` ([[22-langgraph-fundamentals-and-supervisor-routing]]) is a Pydantic
object that flows *through* one graph invocation and is discarded when it ends —
that's the right design for passing data between nodes in a single run. But nothing
downstream of the graph ever looked at that state again:
`interpose.control_plane.runner.run_forever` calls `graph.ainvoke(...)` and discards
the return value entirely on success, logging only on an exception. Agent A1's risk
score fared slightly better — it was written to a Redis hash
(`interpose:session:{session_id}`) — but that hash gets overwritten on every
decision, so it only ever holds the *current* value, never a history.

None of this was a bug. Nothing before this work needed the history — it just meant a
dashboard panel asking "how many high-severity anomalies fired this month" had
nothing to query.

## The fix: three small tables, written where the data already exists

`interpose.control_plane.models` adds `anomaly_flags`, `incidents`, and
`risk_score_snapshots` — plain SQLAlchemy tables sharing `interpose.audit.models.Base`
(same reasoning as `interpose.analytics.models`: one Alembic migration history, not a
second declarative base). Each of Agent A1/A2/A4's node closures already has a
`session_factory` bound in from `build_graph` (that's how they query the audit log for
features/signals) — so persisting the result is just one more `session.add(...)` in
the same closure, right where the value already exists, before it's handed back to
LangGraph and forgotten.

The Redis write and the new Postgres write coexist rather than one replacing the
other, because they serve different readers: Redis's `interpose:session:{id}` hash is
the cheap, current-value read another in-flight agent might want *right now*; the new
`risk_score_snapshots` table is the durable history nothing could query before.

## No foreign key back to `audit_entries`

Every new row carries a `DecisionEvent.audit_id`, but none of the three tables
declares a foreign key against `audit_entries.id`. That's a deliberate choice, not an
oversight — it matches the precedent `interpose.analytics.models.AuditEntrySynthetic`
already set for its own `parent_id` column: a `DecisionEvent` only ever exists because
the gateway already wrote a real audit row and published the event afterward, so the
id is trusted as real in production. But several of this project's own control-plane
tests construct a `DecisionEvent` with a fixed placeholder `audit_id` that was never
actually seeded — a hard FK would force every one of those tests to seed a matching
row just to satisfy a constraint nothing downstream needs enforced.

## Why these tables skip the Spark aggregation step

Day 15's four dashboards mostly read from `agg_*` tables that
`interpose.analytics.aggregate_telemetry` (a Spark job) pre-computes — necessary
there because the demo's synthetic corpus is 10 million rows, too large for a
dashboard panel to `GROUP BY` at interactive speed. Real control-plane traffic runs
at real-gateway scale: tens to low thousands of rows in this project's own dev and
demo use, not millions. The two new Grafana panels
(`charts/interpose/files/dashboards/02-policy-governance.json`,
`03-aml-pack.json`) query `anomaly_flags`/`incidents`/`risk_score_snapshots`
directly with a plain `WHERE created_at >= now() - interval '30 days'` — building a
Spark pre-aggregation step for data this size would be more machinery, not more
"production-grade."

That volume difference is also why these panels carry a `timeFrom: "30d"` override
instead of following the dashboard's own fixed time range: the other panels on these
same dashboards intentionally point at Day 15's fixed synthetic window
(2026-07-06 to 2026-08-03), but this data is real and generated whenever the
control plane actually runs — a fixed historical window would just show it as empty.

## A real test-isolation bug this surfaced

`tests/integration/conftest.py`'s `clean_state` fixture truncated `audit_entries`
before every test, but not these three new tables — invisible as long as a test
suite only ran once. Running the full suite twice in a row (exactly what happened
while building this) broke a test that asserted "exactly one row for this
session_id": the second run's row landed on top of the first run's leftover one.
Fixed by adding all three tables to the same truncation statement — a reminder that
"passes once" and "passes on repeat" are different bars, and only the second one
means the test is actually isolated.
