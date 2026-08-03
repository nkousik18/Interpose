# Response-side policy evaluation, the custom-policy plugin, and two real protocol bugs

Follows [[16-policy-engine-composition]] and [[17-fail-closed-policy-enforcement]]
(request-side, Stage 5) and [[15-fastapi-and-the-naive-proxy]] (why responses stream).
Phase 3 Day 14; `docs/INTERPOSE_SCOPING.md` Section 9.8 — the first real, working
policy pack (`policies/packs/aml/`).

## Why Stage 8 needed real engineering, not just a YAML file

`pii_redaction` and `hitl_gate` both parsed since Day 3, but only `hitl_gate` became
real (Day 6). The reason `pii_redaction` stayed a stub for 11 more days is concrete,
not accidental: the gateway's response path (`_forward`) only ever streams raw,
unparsed bytes straight through (`aiter_raw()`) — nothing has ever looked inside a
response. Redacting PII, or reading `structuring_check`'s `flagged` field for an
alert policy, both need the response *parsed*, not just relayed.

The fix (`_forward_buffered`, `interpose.gateway.app`) only buffers and parses when
`PolicySet.has_response_side_policies` is true for the specific `{server, tool}` being
called — every other call (the overwhelming majority, with no such pack loaded) keeps
the exact streaming path that's worked since Day 1. This matters because the *other*
transport mode this gateway proxies — the long-lived GET stream for server-initiated
messages — genuinely can't be buffered (concept 15); the fix had to be scoped to
`tools/call` responses specifically, never applied blanket.

## The custom-policy plugin: a security boundary, not a convenience

Two of Section 9.8's seven policies (`aml-sanctions-required`, `aml-structuring-alert`)
need real logic no declarative YAML rule can express — one queries session history,
the other reads a specific field out of a specific tool's response. The tempting
shortcut is letting policy YAML embed a snippet of Python to `eval`. That's rejected on
purpose: a policy pack is data a deployer drops into `config/policies` at runtime, and
data that can execute arbitrary code stops being a policy and becomes a code-injection
vector. Instead, `CustomEffect.name` looks up a function in a small registry
(`interpose.policies.custom.REQUEST_POLICIES`/`RESPONSE_POLICIES`), populated by
explicit `@register_request_policy("name")` decorators in code that ships with the
image (`interpose.policies.packs.aml`). A pack can *reference* logic; it can't
*smuggle in* logic.

## Bug 1: `Mcp-Session-Id` doesn't mean what a cross-server policy needs it to mean

The first version of `aml-sanctions-required` correlated "did this session already
check sanctions" via `AuditEntry.session_id`. It never once passed, live-tested or
not — confirmed by opening two real connections through the same gateway to two
different upstream servers and comparing the session IDs each one got back:
completely different values, every time. `Mcp-Session-Id` is assigned by *each
server*, independently, during *its own* `initialize` handshake (per the streamable-
HTTP spec) — it was never meant to identify a caller across multiple upstream
connections, only one connection to one server.

The fix uses `agent_id` instead — extracted from the `Authorization` header
(`_extract_agent_id`), which is under the *calling agent's* control, not
server-assigned. `agents/aml-investigator`'s `InvestigationClient` now sends one
`Authorization: Bearer investigation-<run id>` header, shared across both its OFAC and
transaction-graph connections, specifically so this correlation is possible. Nothing
validates that token — there's no real authentication in this project yet — it's
just a stable identity, reused for exactly the purpose it already existed for.

## Bug 2: `tools/call` responses are SSE-framed, not bare JSON

The first version of the buffered response path did `json.loads(raw_body)` directly.
It failed on the very first live call: FastMCP's streamable-HTTP transport responds
`Content-Type: text/event-stream` for every `tools/call`, framing the JSON-RPC message
as `event: message\ndata: {...}\n\n`, never as a bare JSON body — confirmed by making a
raw `httpx` request and reading the actual response back. `_decode_mcp_body`/
`_encode_mcp_body` parse and re-emit that framing explicitly now, falling back to
plain JSON only if a future upstream ever responds that way instead. Getting this
wrong wouldn't have been a subtle bug — every single buffered call would have failed
outright, which is exactly what happened the first time this path ran against a real
server instead of being assumed correct from the protocol docs alone.

## Named, deliberate gaps in this pack

Not silently dropped — see `policies/packs/aml/README.md` for the full reasoning:

- **`aml-sanctions-required` is agent-level, not per-account.** OFAC's tools take a
  name; transaction-graph's take an account ID. There's no shared key to verify the
  account being queried is the one that was actually screened.
- **`aml-rate-limit-sanctions` only enforces one of the doc's two thresholds** (60/min,
  not also 500/hour) — `RateLimitEffect` would need a bigger schema change to carry
  both, for one policy's second number.
- **`aml-cost-cap` (P7) is a schema-only stub, and deliberately not an active pack
  policy** — the gateway has zero visibility into LLM token cost (an agent's LLM
  calls happen out-of-process), so there's no partial enforcement to fall back to;
  activating it would make every AML-pack-governed call raise `NotImplementedError`.

## Related

- [[16-policy-engine-composition]]
- [[17-fail-closed-policy-enforcement]]
- [[15-fastapi-and-the-naive-proxy]]
- [[21-redis-and-the-hitl-hold]]
- [[30-client-agents-vs-control-plane-agents]]
