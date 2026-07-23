# The hash-chained audit log

Follows [[18-postgres-sqlalchemy-alembic]] (the storage layer this runs on) and
[[17-fail-closed-policy-enforcement]] (the policy decisions this now records
permanently). Implements `docs/INTERPOSE_SCOPING.md` Section 6.7 / G3.

## What "tamper-evident" means, and how a hash chain gets you there

A regular database table can be edited in place — an `UPDATE audit_entries SET
status='COMPLETED' WHERE id=42` leaves no trace that anything ever said otherwise.
For an audit log a regulator might rely on, that's disqualifying: the whole point is
being able to say "this record has not been altered since it was written," not just
"this is what the record currently says."

A **hash chain** makes alteration *detectable* (not impossible — Postgres itself isn't
defended against a privileged attacker who can edit rows directly; see the scoping
doc's own admission of this in Section 8's risk register). Each entry stores a hash of
its own content plus a link to the previous entry's hash:

```
this_hash = SHA-256(prev_hash || canonical_json(entry_without_this_hash))
```

Change anything about entry #42 after the fact — its `tool`, its `decision`, its
`timestamp` — and recomputing its hash produces a different value than what's stored.
Worse for the tamperer: entry #43 recorded #42's *original* `this_hash` as its own
`prev_hash`, so the break is visible looking forward from the point of tampering, not
just at the tampered row itself. `interpose.audit.chain.verify_chain` is exactly this
recomputation, walking entries in order and reporting the first mismatch — proven in
`tests/integration/test_gateway_audit.py::test_tampering_with_a_stored_row_is_detected`,
which really does `UPDATE`s a live Postgres row and confirms verification catches it.

**The genesis hash.** The very first entry has no real predecessor, so it points to a
well-known placeholder — 64 hex zeros here (`chain.py`'s `GENESIS_HASH`) — so
verification has something concrete to check the first entry against instead of a
special-cased "skip the check for entry one."

**What's deliberately left out of the hash.** The database's own auto-incrementing
`id` isn't part of the hashed content — it's a storage detail (which row number
Postgres happened to assign), not something about the *call* being recorded. Chain
order comes entirely from `prev_hash` → `this_hash` pointers, which is what makes the
chain's integrity independent of anything Postgres itself does with row numbering.

## Why one call sometimes produces two rows, never one updated in place

`AuditEntry.status` can be `INTENT`, `COMPLETED`, `DENIED`, `HELD`, or
`UPSTREAM_ERROR` — but a row is never moved between these by an `UPDATE`. A denied
call gets one `DENIED` row, full stop: there was never anything pending. An allowed
call gets an `INTENT` row *before* the upstream is called (Stage 6) — so the audit
log shows the gateway's intent even if the forward step itself crashes — and then a
second `COMPLETED` (or `UPSTREAM_ERROR`) row afterward, linked back via `parent_id`
(Stage 8). Two append-only rows, not one row with a status column that changes
underneath you — which is also exactly what the append-only writer role the scoping
doc describes (INSERT-only, no UPDATE/DELETE grant) forces you into structurally, even
before anyone configures database permissions to enforce it. (That role restriction
itself isn't wired up yet — noted as a real gap, not implemented this session.)

## Serializing writers: an advisory lock, not a queue

Building entry N+1 requires knowing entry N's `this_hash` first. Two requests being
audited at the same instant could both read "the latest hash is X" and both try to
build on X — corrupting the chain (two entries would each legitimately claim to be
next). `interpose.audit.store.AuditStore` prevents this with a Postgres **advisory
lock** (`pg_advisory_xact_lock`): a lock the *application* defines the meaning of
(Postgres just tracks who's holding key `8_784_213_001` right now), scoped to the
transaction, so concurrent writers queue up one at a time for the brief window of
"read the latest hash, compute the next one, insert." Everything outside that window
(policy evaluation, the actual upstream call) still runs fully concurrently.

## A deliberate MVP simplification: whose clock is authoritative

Section 6.7 wants Postgres's own server time as authoritative (NTP-synced, harder for
a compromised application to lie about than its own clock). But the hash needs every
field's value *before* the row is inserted — and a value Postgres assigns via
`server_default` (like `now()`) isn't known until after insert, with no way to fix it
up afterward without an `UPDATE` the append-only design rules out. This MVP uses the
application's own clock (`datetime.now(UTC)`, set explicitly in Python before hashing)
instead. The scoping doc already flags real timestamp signing as v0.2 scope for
regulated deployments (Section 8) — this is the same tradeoff, made now rather than
later, and written down rather than silently assumed.

## Related

- [[18-postgres-sqlalchemy-alembic]]
- [[17-fail-closed-policy-enforcement]]
