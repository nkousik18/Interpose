# The policy engine: a declarative DSL, and how effects compose

## Why a DSL instead of Python if/else

Interpose's policy engine ([[02-interpose-gateway-overview]]) needs a compliance
officer, not just a developer, to be able to add a rule like "block delete calls on
the transaction-graph server" without touching Python. So policies are written as YAML
(`docs/INTERPOSE_SCOPING.md` Section 6.6) and validated into typed Pydantic objects
(`src/interpose/policies/schema.py`) rather than being if/else branches in the
gateway's code. This is the same reason infrastructure teams use Terraform/Helm
instead of shell scripts: the *rules* become data, reviewable and diffable
independent of the engine that executes them.

**Pydantic discriminated unions.** A policy's `effect` field can be one of several
different shapes (`allowlist`, `denylist`, `rate_limit`, ...) depending on its `type`
key. Pydantic's discriminated union (`Field(discriminator="type")` over an
`Annotated[A | B | C, ...]`) uses that `type` value to pick which of several models to
validate against, and rejects anything that doesn't match one of them. This is what
makes `Policy.model_validate(...)` able to load five structurally different kinds of
policy through one field, with a real validation error (not a silent mismatch) if
someone writes `type: bocklist` by typo.

## Effect types and evaluation order

Section 6.5's Stage 5 fixes an evaluation order — `allowlist → denylist → rate_limit →
pii_redaction → hitl_gate → custom` — and says the first *terminal* outcome (allow,
deny, or hold) wins. Only the first three exist yet
(`docs/ROADMAP.md` Phase 1 Day 2); PII redaction and HITL gate are stubbed in Day 3.

## The one genuinely non-obvious rule: what an allowlist actually does

It would be natural to assume an `allowlist` effect just means "this specific tool is
fine" — additive, with no side effects elsewhere. That's not how it's implemented, and
deliberately not: **writing even one allowlist policy for a server flips that whole
server to default-deny.**

Concretely: if `transaction-graph` has one allowlist policy naming `read_balance`,
then `read_balance` passes — but `mark_investigated` is now *denied*, even though no
one ever wrote a denylist rule for it. A server with zero allowlist policies is
unaffected; every tool on it stays default-allow, exactly as if no policy pack
existed at all.

This mirrors how allow-lists work in most real infrastructure — AWS security groups,
Kubernetes `NetworkPolicy`: the first allow rule for a scope is what turns on
enforcement for that scope, not a separate "enable enforcement" switch. It means a
compliance officer writing "only `read_balance` is allowed" doesn't also have to
remember to write a denylist rule for every other tool that exists today — or every
tool added tomorrow. The tradeoff, and the reason this is worth writing down rather
than leaving implicit: an allowlist rule is quietly more powerful than it looks. Adding
one is not just "permit this," it's "restrict everything else on this server too."

(See the same rule spelled out next to the code that implements it:
`src/interpose/policies/policyset.py`, `PolicySet.evaluate`.)

## Compilation and hot reload, without a real reload mechanism yet

Stage 4 calls for the composed `PolicySet` for a `{server, tool}` pair to come from
"an in-memory cache (invalidated on config reload)." `PolicyEngine`
(`policyset.py`) is that cache: it's built once from a full policy list, and lazily
compiles + memoizes a `PolicySet` (the applicable policies, already sorted into
evaluation order) the first time a given `{server, tool}` pair is requested.

There's no reload trigger wired up yet (that's a later phase), but the shape already
matches what one will look like: a `PolicyEngine` is immutable once built, so a reload
is "construct a new `PolicyEngine` from the reloaded policy list and swap the
reference" — never mutating one in place. That's what makes the eventual hot reload
atomic: in-flight requests keep using the `PolicyEngine` they started with.

## Rate limiting: a deliberately temporary implementation

`RateLimiter` in `policyset.py` is an in-memory fixed-window counter — correct for a
single process, but it would give every gateway replica its own independent counter
in a real multi-replica deployment, which isn't good enough for production rate
limiting. Section 6.8 already specifies the real target: Redis, with atomic
`INCR`+`EXPIRE`. The two share the same `check_and_increment(key, limit, window) ->
bool` interface on purpose, so swapping the in-memory version for a Redis-backed one
later is a one-class change, not a rewrite of the policy evaluation logic that calls
it.

## Related

- [[02-interpose-gateway-overview]]
- [[15-fastapi-and-the-naive-proxy]]
