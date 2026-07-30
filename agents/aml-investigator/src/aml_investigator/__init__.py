"""AML Investigation Agent (docs/INTERPOSE_SCOPING.md Section 9.7, Phase 3 Day 13).

A *client* of Interpose, not part of it -- this is the pretend AML analyst assistant
that receives a suspicious-transaction alert and drives the investigation entirely by
calling MCP tools through the gateway, exactly like any other external agent would.
Every tool call here is ordinary gateway traffic: it gets a policy decision and an
audit entry the same as anyone else's, which is the whole point of using it as the
demo. Contrast with `interpose.control_plane`, which lives *inside* Interpose and
never makes tool calls itself -- it only ever reacts to `DecisionEvent`s the gateway
already recorded. See concepts/30-client-agents-vs-control-plane-agents.md.

Lives under `agents/` (Section 6.16), deliberately outside `src/interpose/`, but
still imports `interpose.control_plane.llm.generate_structured` for its two LLM
nodes rather than re-implementing the same Groq strict-schema wrapper a second time.
This is a different situation from `mcp-servers/`, which must have zero coupling to
`interpose` internals to be believable as independent third-party services the
gateway proxies to -- this agent has no such fiction to maintain; it's Interpose's
own demo client, running in the same installed environment.
"""
