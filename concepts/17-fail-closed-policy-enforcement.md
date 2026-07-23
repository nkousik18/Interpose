# Wiring policy into the gateway: fail-closed, and denying inside the protocol

Follows [[16-policy-engine-composition]] (the policy engine itself) and
[[15-fastapi-and-the-naive-proxy]] (the gateway it's now wired into). This is Phase 1
Day 3 (`docs/ROADMAP.md`): Stages 4-5 of the request lifecycle
(`docs/INTERPOSE_SCOPING.md` Section 6.5) are now live in
`src/interpose/gateway/app.py`.

## A denial is a JSON-RPC error, not an HTTP error

Day 1's route resolution failure (unknown server) returns a normal HTTP 404 — that's a
proxy-level problem, the agent never got as far as talking MCP at all. A policy denial
is different: the agent's request was completely valid MCP, addressed to a server that
exists, asking for a tool that exists. The *gateway* is choosing not to forward it.
That's not a transport failure, so it shouldn't look like one.

Instead, a denial comes back as HTTP 200 containing a **JSON-RPC error object**,
addressed to the same request `id` the agent sent:

```json
{"jsonrpc": "2.0", "id": 3, "error": {"code": -32001, "message": "policy_denied", "data": {"policy": "hello-echo-no-dangerous-tool", "reason": "..."}}}
```

This is exactly the shape the MCP Python SDK already expects for an in-protocol
error — its `ClientSession` recognizes an `error` field on a response and raises
`McpError` from it automatically (see `tests/integration/test_gateway_policy.py`,
which catches exactly that and reads `exc.error.message` / `exc.error.data`). The
error code (`-32001`) sits in the `-32000` to `-32099` range JSON-RPC 2.0 reserves for
implementation-defined server errors — not one of the protocol's own reserved codes
(parse error, invalid request, etc.), because this isn't a protocol violation.

## Fail-closed: what it means, and why it's not just "add a try/except"

Section 6.5 states the rule directly: *if the policy engine itself errors, the
default outcome is DENY, not PASS.* This is the opposite of how most application code
handles unexpected exceptions (log it, maybe return a generic 500, definitely don't
silently let the risky action through) — and for a governance gateway specifically,
letting a tool call through *because the thing meant to evaluate it crashed* would be
the single worst failure mode available. A bug in policy evaluation must never look
like an allow.

`_evaluate_policy` in `app.py` implements this literally: the whole
`policy_engine.compile(...).evaluate(...)` call is wrapped in a bare
`except Exception`, and any exception — the deliberate `NotImplementedError` from an
unenforced `hitl_gate`/`pii_redaction` policy included — becomes
`PolicyDecision(DENY, reason="policy_engine_error")`, logged with a full traceback
(`logger.exception`, not swallowed). The exception's *content* is diagnostic
information for whoever reads the logs; its *consequence* is always the same: deny.

## What policy governs, and what it doesn't

Only `tools/call` requests reach the policy engine at all. Everything else —
`initialize`, `list_tools`, `notifications/initialized`, the long-lived GET stream for
server-initiated messages — bypasses Stage 4-5 entirely and forwards exactly like Day
1. This isn't a gap to close later; it's the correct scope. A policy's `applies_to`
is defined in terms of `{server, tool}` ([[16-policy-engine-composition]]) — there's no
tool to check a policy against when an agent is just asking "what tools exist,"
and gating the handshake itself would break MCP for every agent, governed or not.

## Related

- [[15-fastapi-and-the-naive-proxy]]
- [[16-policy-engine-composition]]
