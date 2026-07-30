# Client agents vs. control-plane agents

Follows [[22-langgraph-fundamentals-and-supervisor-routing]] and
[[25-remaining-control-plane-agents]]. Phase 3 Day 13;
`docs/INTERPOSE_SCOPING.md` Section 9.7 — the AML investigation agent
(`agents/aml-investigator/`).

## Two LangGraph systems, doing opposite jobs

Interpose now has *two* separate LangGraph graphs, and it's worth being precise about
why they're not the same kind of thing, even though both are "a LangGraph agent":

- **The control plane** (`interpose.control_plane`, Phase 2) lives *inside* Interpose.
  It never calls an MCP tool. It only ever reacts to a `DecisionEvent` the gateway
  already recorded, after the fact — enriching it, maybe flagging an anomaly, maybe
  composing a HITL narrative. Its job is to make sense of traffic that already
  happened.
- **The investigation agent** (`agents/aml-investigator/`, Phase 3) is a *client* of
  Interpose — a pretend AML analyst assistant. It calls MCP tools *through the
  gateway*, exactly like Claude Code, a LangChain agent, or any other real MCP client
  would. Every one of its tool calls is ordinary gateway traffic: it gets a policy
  decision and an audit entry the same as anyone else's. Its job is to *generate* the
  traffic the control plane and audit log then have something to observe.

This is also why the investigation agent lives under `agents/`, not
`src/interpose/control_plane/` — it isn't part of the product Interpose ships. It's
the demo's stand-in for "some external agent using Interpose," playing the same role a
real bank's investigation tooling would.

## Why a linear graph, not a ReAct loop

A more familiar LangGraph pattern is a single "agent" node in a loop: the LLM sees the
available tools, decides which one to call next, sees the result, decides again, until
it's satisfied. The investigation agent deliberately does **not** work this way.
Section 9.7 specifies a fixed 5-node procedure — Discovery → Enrichment → Assessment →
Recommendation → Report — where each node calls a specific, named set of tools in a
specific order, and only two of the five nodes (Assessment, Report) involve an LLM at
all.

This is a real design choice, not a simplification of "the real thing": a compliance
investigation procedure is supposed to be reproducible and auditable — a reviewer
should be able to say "yes, the agent did the sanctions check before recommending a
disposition" as a *guarantee*, not as something that happened to occur this run. A
free-roaming ReAct loop can't promise that; a fixed graph can. The LLM's job here is
narrower and more honest about what LLMs are good at: reasoning over evidence
(Assessment) and writing prose (Report), not deciding investigative procedure.

## Reusing the LLM wrapper across a boundary that otherwise stays clean

`mcp-servers/ofac-sanctions` and `mcp-servers/transaction-graph` deliberately have zero
dependency on `interpose` internals — the whole point is that they stand in for
independent, real third-party services the gateway proxies to, and a real production
sanctions API obviously isn't built out of Interpose's own code.

The investigation agent breaks that pattern on purpose: its Assessment and Report
Composer nodes import `interpose.control_plane.llm.generate_structured` directly,
rather than a second hand-rolled Groq client. There's no fiction to protect here — this
agent *is* Interpose's own demo client, not a pretend-independent service — and
`generate_structured` already carries two hard-won fixes from
[[24-narrative-generation-with-a-real-llm]] (Groq's `additionalProperties: false`
requirement, `gpt-oss`'s reasoning-token budget). Re-implementing that wrapper a second
time would mean carrying those same two bugs twice, for no isolation benefit anyone
actually needs. Every LLM node still takes an injectable `generate_fn`, the same seam
every control-plane agent already exposes, so the automated test suite never needs a
real API key.

**Live-verified**, not just unit-tested: with this repo's own `.env` `GROQ_API_KEY`, a
real end-to-end run against fixture data produced a valid `Assessment` and
`InvestigationReport` on the first real Groq call — no schema failures, no fallback
triggered. The fallback path itself (deterministic risk heuristic, deterministic
report summary) is what the automated suite actually exercises, same division of labor
as Day 8.

## A real bug the seed generator's own tests caught

The seed alert generator (`aml_investigator.seed.pick_seed_alert`) picks a real
labeled-laundering transaction from the subsampled dataset to start a demo run from.
The first version picked a "random" row via `OFFSET (seed % 97)` against the
laundering-labeled subset. Against the real dataset (35,230 laundering transactions)
this works by accident — offset 42 is nowhere near running out of rows. Against this
module's own tiny test fixture (2-3 rows), the fixed modulus produced an offset far
past the end of the result set, and the query returned nothing. Fixed by bounding the
offset to the actual candidate count (`seed % total`, computed from a real `count(*)`
first) instead of a number that happened to be big enough for one specific dataset.
Exactly the kind of bug that only shows up once something exercises the code path with
a different data shape than the one it was written against — the same lesson as
[[29-embedded-analytics-with-duckdb]]'s CSV-vs-Parquet type-inference bug.

## Related

- [[22-langgraph-fundamentals-and-supervisor-routing]]
- [[24-narrative-generation-with-a-real-llm]]
- [[25-remaining-control-plane-agents]]
- [[28-fuzzy-matching-and-sanctions-screening]] — the `structuredContent` envelope
  quirk this agent's MCP client also has to unwrap, including for `check_entity`'s
  `Model | None` union return type.
- [[29-embedded-analytics-with-duckdb]]
