# Narrative generation with a real LLM (Groq), and two bugs only a live call could catch

Phase 2 Day 8 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Sections
7.7-7.10's LLM usage. First real LLM integration in the project.

## Why Groq, and why that's not a deviation from the plan

Section 6.4 names Anthropic Claude as Interpose's default LLM provider, but in the
same breath calls out Groq as an anticipated alternative, and makes the provider a
`Settings`-level swap, not a hardcoded choice. Groq is configured today for a concrete
reason: it has a genuinely free tier, and this project's owner didn't want per-call
billing while iterating on prompts during development. `interpose.control_plane.llm`
is the whole surface that would need to change to swap to Claude later —
`generate_structured`'s signature stays the same; only what's inside talks to a
different SDK.

## Real structured outputs, not prompt-and-hope JSON

The lazy version of "make the LLM return JSON" is: ask nicely in the prompt, then
`json.loads()` the response and hope. Groq (like OpenAI) supports something stronger:
`response_format={"type": "json_schema", "json_schema": {..., "strict": True}}`
constrains what tokens the model can even generate at each step, so it's structurally
incapable of producing output that doesn't match the schema — not just "usually
doesn't." Passing a Pydantic model's own `model_json_schema()` as that schema is what
makes Section 7's requirement ("Structured JSON output constrained by Pydantic; no
free-form response") literally true rather than aspirational.

## Two bugs that only existed because a live call was actually made

Every agent's LLM call is unit-tested with a **mocked** Groq client — deterministic,
free, no network, and that's deliberate (below). But mocks only test that your code
sends what you *think* it sends; they can't catch the real API rejecting something
your code got wrong. Two real bugs surfaced only once an actual API key was
configured and a real call was made:

**Bug 1 — Groq's strict mode requires `additionalProperties: false` on every object
in the schema.** Pydantic's `model_json_schema()` doesn't set this by default. The
very first live call failed with `invalid JSON schema for response_format:
'additionalProperties:false' must be set on every object`. Fixed by
`_strict_schema()`, which walks the generated schema (including nested `$defs`) and
injects it — centralized in the LLM wrapper itself, so every current and future
structured-output call gets this automatically rather than relying on each output
model remembering a `model_config` setting.

**Bug 2 — reasoning models can exhaust the token budget before producing any output
at all.** `openai/gpt-oss-20b` (the configured model) does hidden reasoning before
its visible answer. At the default reasoning effort, Agent A4's longer 5-8-sentence
prompt burned through `max_completion_tokens` entirely on reasoning tokens, and the
API returned `max completion tokens reached before generating a valid document` —
no JSON at all, not even a malformed one. Fixed by requesting `reasoning_effort="low"`
for every call: these are short, low-ambiguity structured-output tasks that don't need
deep reasoning, and the fix leaves the token budget for the part that actually
matters.

Neither of these would have been caught by mocked unit tests alone, no matter how
thorough — they're facts about the real API's contract, not about this project's own
logic. That's the specific, concrete argument for why "build it, then do one real
smoke test before calling it done" earns its keep, beyond general due diligence.

## Why the automated test suite still never calls the real API

Every agent's LLM dependency is injected (`generate_fn`, defaulting to the real
`generate_structured`) — the same dependency-injection seam already used for
`session_factory` and `redis_conn` elsewhere in the control plane. Unit tests patch
`AsyncGroq` itself to return canned responses; the graph-level integration tests
(`tests/integration/test_control_plane_graph.py`) go further and rely on
`generate_structured`'s own **fallback path**: when no `GROQ_API_KEY` is configured,
every LLM-dependent agent produces a clear, deterministic fallback narrative instead
of failing outright (see concept 25) — so those tests exercise real resilience
behavior, not a workaround.

This created a real, worth-naming hazard: once a developer adds a real key to their
local `.env` for manual smoke-testing (exactly as done above), every one of those
"fallback path" tests would silently start calling the *real* API instead —
different behavior locally than in CI, and real billed calls hiding inside what looks
like a deterministic test run. `tests/conftest.py` forces `GROQ_API_KEY=""` for the
entire test session, unconditionally, before any test module is imported — the
automated suite's behavior no longer depends on what happens to be in anyone's local
environment.

## Related

- [[25-remaining-control-plane-agents]]
- [[23-control-plane-event-bus-and-feature-engineering]]
