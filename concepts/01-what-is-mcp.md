# MCP (Model Context Protocol)

## What it is

MCP is a standard way for an AI agent (or any LLM-powered application) to call external tools
— query a database, look up a sanctions list, send a Slack message, read a file — without the
agent's creator having to hand-write a custom integration for every single tool.

It defines two roles:
- **MCP server**: exposes a set of "tools" (functions with a name, description, and input
  schema) that it knows how to execute. E.g. an "OFAC sanctions" MCP server might expose a tool
  called `check_name` that screens a name against a sanctions list.
- **MCP client**: something that connects to one or more MCP servers, discovers what tools they
  offer, and calls them on behalf of an agent or LLM.

The protocol itself is just the wire format and handshake — how a client discovers tools, how
it calls one, how results and errors come back. It says nothing about *whether a given call
should be allowed to happen*. That gap is exactly what Interpose exists to fill — see
[[02-interpose-gateway-overview]].

## Why it exists

Before a standard like this, every AI product that wanted to call external tools had to build
its own bespoke plumbing per tool, per vendor. MCP is an attempt to do for "AI agent calls a
tool" what HTTP did for "one computer talks to another": a shared protocol so tool builders and
agent builders don't have to coordinate pairwise. Anthropic introduced it and it's now used
across the industry (Section 3 of the scoping doc names Anthropic/Linux Foundation AAIF as one
of the audiences for this project, for that reason).

## Why it matters for this project

Interpose's entire reason for existing depends on one fact: MCP defines *how* a tool call
happens, but has no built-in concept of policy, approval, or audit trail. In a world where
agents are given more and more ability to take real actions, "the protocol works" and "the
protocol is safe to give production access to" are different claims. Interpose adds the second
one without changing MCP itself or requiring agents/servers to be rewritten — which is only
possible *because* MCP is a standard protocol with a defined wire format Interpose can sit in
the middle of.

## Key vocabulary

- **Tool**: a single callable capability an MCP server exposes (e.g. `check_name`,
  `get_account_transactions`). Has a name, a description (so the LLM knows when to use it), and
  a JSON schema for its inputs.
- **Tool call**: an agent invoking a specific tool with specific arguments. This is the unit
  Interpose intercepts, evaluates, and logs.
- **Transport**: how bytes actually move between client and server. MCP supports a couple of
  transports; the scoping doc commits to "Streamable HTTP first, stdio later" (Section 6.17) —
  we'll cover what that means concretely when we build the gateway's ingress stage.

## Related

- [[02-interpose-gateway-overview]] — what Interpose adds on top of MCP, and why.
