# Interpose: what it is and why it's shaped this way

## The problem, in plain terms

Imagine an AI agent that's allowed to query a bank's transaction database and, eventually, file
compliance reports. It talks to those systems via MCP tools (see [[01-what-is-mcp]]). Two
questions MCP itself never answers:

1. **Should this specific call be allowed right now?** Maybe the agent should be able to *read*
   transactions freely but needs a human to sign off before it takes any action with real-world
   consequence.
2. **What actually happened, and can we prove it?** If a regulator, auditor, or incident
   responder asks "what did this agent do and why," there needs to be a trustworthy record —
   not just application logs someone could have edited after the fact.

Interpose answers both by sitting *between* the agent (MCP client) and the real tool servers
(MCP servers), as a transparent proxy: from the agent's point of view it looks like a normal
MCP server; from the real tool server's point of view it looks like a normal MCP client. Every
call passes through it.

## What it does to each call

Roughly, for every tool call that flows through:

1. **Evaluate it against policy** — a set of rules like "deny this tool entirely,"
   "redact PII fields in the response," "require a human to approve this before it proceeds,"
   or "rate-limit this agent to N calls/minute." We'll go deep on this in a dedicated policy
   engine concept doc once we build it.
2. **Write an audit record** — before *and* after the call, so there's a record even if the
   call never completes. These records are chained together with hashes so that tampering with
   one after the fact becomes detectable (a dedicated concept doc will cover audit/hash-chaining
   when we build it — this is a meaty topic on its own).
3. **Forward, deny, or hold it** — based on what policy decided.

## Why a proxy, not a library or a fork of MCP

Three deliberate choices, each for a reason:

- **Proxy, not a client-side library**: a library only helps the agents that choose to import
  it. A proxy sitting on the network path governs *any* MCP client, regardless of what agent
  framework built it — which matters a lot for an enterprise that has many teams building
  agents independently and wants one governance point, not N.
- **Transparent, not a fork/extension of MCP**: Interpose doesn't add custom fields to the MCP
  protocol or require servers to know about it. That's what "transparent" means here — neither
  side has to change for Interpose to work. That keeps it usable with *any* MCP server or client
  that already exists.
- **Deny/allow/redact/hold as first-class policy outcomes**: chosen because these map directly
  to what a real compliance or platform team already thinks in terms of — "who can do what,"
  "what needs a human," "what's sensitive and must be scrubbed" — rather than inventing new
  governance vocabulary.

## The three "planes"

The scoping doc splits Interpose's internals into three planes with very different speed
requirements — this shows up constantly, so it's worth having the mental model early:

- **Data plane**: the actual proxying, on the hot path of every single call. Needs to be fast
  (target: under 100ms added latency at the 99th percentile — see
  [[03-sla-slo-latency-budgets]] for what that means and why it's the right way to state a
  performance target).
- **Control plane**: a set of LangGraph agents that look at what's happening (decisions,
  patterns across calls) and enrich it — e.g. flag anomalies, compose human-readable evidence
  for an incident. Runs asynchronously, seconds behind the data plane, because it's allowed to
  think longer.
- **Analytics plane**: batch jobs (Spark) that crunch the accumulated audit history into
  dashboards, on a much slower cadence (every 15 minutes). No latency pressure at all.

Splitting these apart is what lets the fast path stay fast (nobody's LLM call blocks a real
tool invocation) while still getting the benefit of slower, smarter analysis elsewhere.

## The demo: why AML specifically

Interpose-the-gateway is domain-agnostic — it would work equally well in front of tools for
customer support, DevOps, or anything else. The project picks **AML (anti-money-laundering)**
as the one worked example because it's a domain where "an AI agent took an action and we need
to prove why" is an unusually concrete, high-stakes, real-world need — which makes for a
convincing demo. See [[04-aml-ofac-glossary]] for the domain vocabulary. Important: the AML
pack is illustrative only, built on public synthetic data — it is explicitly *not* a real
compliance product (the scoping doc is emphatic about this in several places).

## Related

- [[01-what-is-mcp]]
- [[03-sla-slo-latency-budgets]]
- [[04-aml-ofac-glossary]]
