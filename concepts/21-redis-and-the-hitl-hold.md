# Redis, and the HITL hold: a blocking wait, deliberately

Phase 2 Day 6 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Section 6.8
and the `hitl_gate` effect first stubbed in [[16-policy-engine-composition]] /
[[17-fail-closed-policy-enforcement]].

## What Redis is, and why it fits this job specifically

Postgres ([[18-postgres-sqlalchemy-alembic]]) is for the audit log: durable,
queryable, needs strong consistency. A HITL ticket is different — it's short-lived
(minutes to hours, never years), gets checked constantly while pending (every poll of
`wait_for_decision`), and should vanish on its own if nobody ever answers it. **Redis**
is an in-memory data store built for exactly that shape of data: fast reads/writes,
and a built-in **TTL** (time-to-live) — set an expiry on a key and Redis deletes it
automatically, no cleanup job required. A ticket's TTL is set to the policy's
`timeout_seconds` plus a small grace period, so an expired ticket disappears from
Redis at roughly the same time the gateway gives up waiting on it.

Two Redis structures do the actual work (`src/interpose/session/hitl.py`):
- `interpose:hitl:{ticket_id}` — a **hash** (Redis's map type), the ticket's fields.
- `interpose:hitl:pending` — a **set** of ticket IDs currently pending, so
  `interpose review list` can find them in one lookup instead of scanning every key
  in the database.

**Deliberately not built yet:** Section 6.8 also describes an
`interpose:session:{agent_id}` hash for session-level state (start time, running risk
score, active tickets). Nothing reads or writes a risk score yet — that's the
anomaly-detection work in Phase 2's control-plane agents (Day 8) — so building that
hash now would be exactly the kind of unused infrastructure this project has
deliberately avoided elsewhere (the in-memory `RateLimiter`
[[16-policy-engine-composition]], deferring Redis itself back on Day 5). It'll arrive
when something actually consumes it.

## The real design question: what does "held" mean over a synchronous protocol?

Section 6.5's Stage 7 says a held call "returns a held response to the agent
immediately" while "the HITL flow takes over." Taken completely literally, that reads
as: reply right away with "this is pending," and somehow let the agent come back
later for the real answer. But MCP's `tools/call` is a normal request/response
exchange — there's no built-in mechanism in the base protocol for "check back later
for this specific call's result," and building one (matching results to original
calls, a poll/webhook endpoint, resuming a session that already closed) is a
significant protocol-design exercise of its own, not a natural fit for a one-day
milestone.

**What's built instead: the gateway blocks, asynchronously, on the same request.**
When a policy evaluates to `HOLD`, the handler:
1. Writes a `HELD` audit row and opens a Redis ticket.
2. `await`s `wait_for_decision` — polling the ticket every 250ms — for up to the
   policy's `timeout_seconds`.
3. Once a reviewer decides (via `interpose review approve/deny`, Day 6's CLI): if
   approved, forwards the call for real and returns the actual result, linked to the
   `HELD` row via `parent_id` exactly like a normal `PASS`; if denied, returns a
   structured `hitl_denied` error; if the timeout elapses with no decision, a
   `hitl_timeout` error.

Because this is `await`-based, not a blocking thread, the gateway keeps serving every
*other* request normally while one call sits waiting — that's the whole point of
having built the gateway async from Day 1. But it does mean an HTTP connection (and
whatever client-side timeout the agent's MCP session has configured) stays open for
as long as the hold lasts, which could be the full hour a real `timeout_seconds: 3600`
policy allows. That's a genuine, known tradeoff of this MVP design, not something to
gloss over: a production system fielding long human-review windows would more likely
use the retry/resume model Stage 7's wording gestures at, or a webhook back to the
agent framework. Block-and-poll was chosen here because it's honestly testable within
a single day (`tests/integration/test_gateway_hitl.py` drives the whole cycle — hold,
concurrent review, resolution — in one `asyncio.gather`), and because MCP's synchronous
tool-call model doesn't offer an obvious simpler alternative without extra protocol
machinery this project hasn't adopted.

## The audit trail this produces

A held call now has three possible shapes, all following the append-only,
`parent_id`-linked pattern from [[19-hash-chained-audit-log]]:
- `HELD` alone with no follow-up would mean the process crashed mid-wait (doesn't
  happen in the tests, but the row exists regardless, same as Day 4's `INTENT`).
- `HELD` → `DENIED` (reviewer said no, or nobody answered in time — `decision.reason`
  distinguishes `hitl_denied` from `hitl_timeout`).
- `HELD` → `COMPLETED`/`UPSTREAM_ERROR` (reviewer approved; the call actually ran).

The schema's `hitl_ticket_id` / `hitl_reviewer` / `hitl_decision` / `hitl_rationale`
columns — defined back in Day 4, unused until now — get populated on whichever
terminal row follows the `HELD` one, so "who approved this, and why" is part of the
permanent, hash-chained record, not just something that happened in Redis and was
forgotten once the ticket expired.

## Related

- [[16-policy-engine-composition]]
- [[19-hash-chained-audit-log]]
