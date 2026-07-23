# LangGraph fundamentals, and the Supervisor's routing design

Phase 2 Day 7 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Section 7
(Agents A0-A1 of the 5-agent control plane). This is the first LangGraph work in the
project — one of the three resume gaps Interpose exists to close.

## What LangGraph actually is

Strip away the "multi-agent" framing for a second: **LangGraph is a state machine
library.** You define a `StateGraph` over some typed state object, add named
**nodes** (each just a function: `state -> partial state update`), connect them with
**edges** (fixed: always go from A to B) or **conditional edges** (a router function
inspects the state and returns which node to go to next), then `.compile()` the whole
thing into a runnable graph you can `.ainvoke(initial_state)` or `.astream(...)` to
watch it execute node-by-node.

What makes it fit *multi-agent* systems specifically is that each node can be "an
agent" (a function that might call an LLM, might query a database, might do neither)
and the graph's edges encode how agents hand off to each other — which is exactly the
shape a supervisor-and-specialists design needs. But there's no framework magic making
an agent an agent; `interpose.control_plane.agents.supervisor` and
`interpose.control_plane.agents.policy_evaluator` are just plain Python functions that
happen to be registered as graph nodes.

**Why a graph instead of hand-written if/else chaining function calls?** Two concrete
reasons visible in this project already:
1. **Introspectable routing.** `graph.astream(state)` yields the exact sequence of
   nodes that ran, in order — `tests/integration/test_control_plane_graph.py` uses
   this directly to prove "a DENY event goes straight to the incident-escalator stub,
   skipping A1 entirely" without needing to add any test-only instrumentation to the
   agents themselves. A hand-rolled call chain doesn't give you that for free.
2. **The topology is data, not code shape.** Section 7.14 ("framework escape hatch")
   makes this explicit: agents are Pydantic-in/Pydantic-out functions, and the graph
   topology is a separate, replaceable definition (`interpose.control_plane.graph`).
   Changing how events route between agents means editing edges in one place, not
   restructuring nested if/else across multiple call sites.

## Typed state, not a chat transcript (P2)

`interpose.control_plane.state.InterposeState` is the object that flows through the
whole graph — every node reads some slots off it and returns a partial update to
others. It's a Pydantic model, not a list of messages or a growing prompt string. This
is a deliberate rejection of the "conversation memory" pattern common in LLM-agent
demos (Section 7.2, design principle P2): a compliance officer (or a future engineer)
should be able to look at `InterposeState`'s field list and know exactly what
information exists at every point in the pipeline, rather than reverse-engineering it
from what's been appended to a transcript so far.

One practical wrinkle worth knowing: LangGraph doesn't hand your node functions actual
`InterposeState` instances — internally it manipulates state as plain dicts, coercing
to/from the Pydantic model at graph boundaries. A node's own return value (partial
update dict) gets merged in as a dict; a node's *input* argument, and the final result
of `.ainvoke()`, come back as dicts too, with nested Pydantic fields (like `enriched`)
present as **actual model instances**, not re-serialized dicts. (`result.get("enriched")`
returns an `EnrichedDecision` object; `result.get("enriched").context_features` is
attribute access, not another dict lookup.) This tripped up the first draft of this
project's own tests — worth knowing before it trips up the next thing built on this
graph.

## The Supervisor's routing: a judgment call between prose and diagram

Section 7.6 describes the routing rule in prose ("If `HOLD`: route to A1 then A3. If
`DENY`: route to A4. If `PASS` and risk above threshold: route to A1 then A2. Else
route to A1 only.") but Section 7.5's ASCII diagram draws three arrows fanning out of
the Supervisor to A1, A2, and A4 *simultaneously*, which reads more like "all three
specialists always run" — a different, parallel-fan-out design.

This project went with the prose, for two reasons: it's more specific (an ASCII
diagram is a sketch; a written rule is a specification), and it matches how a
"supervisor" pattern is normally understood in orchestration systems generally — a
dispatcher choosing a conditional path per event, not a broadcaster. Concretely, this
becomes **two sequential conditional hops**, not one:

1. `route_after_supervisor` — runs immediately after the Supervisor node, before
   anything has enriched the event. Its only job: does this event skip straight to
   A4 (`DENY`), or does it go through A1 like everything else?
2. `route_after_policy_evaluator` — runs after A1 has actually enriched the event
   (so `state.enriched.session_risk_score` exists to check). Decides between A3
   (`HOLD`), A2 (`PASS` + risk above threshold), or ending there.

Both are ordinary Python functions, unit-tested directly with a 20+-case matrix
(`tests/unit/control_plane/test_supervisor.py`) exactly as Section 7.6 specifies for
this agent's testing approach — no graph needed to verify the routing *logic* is
correct; the graph-level tests separately verify the routing is *wired up* correctly.

## Stub nodes: building the real edges before the real agents exist

Only A0 (Supervisor) and A1 (Policy Evaluator) do real work as of Day 6. Agents A2
(Anomaly Detector), A3 (Evidence Composer), and A4 (Incident Escalator) don't exist
until Phase 2 Day 8 — but the graph's conditional edges already need *somewhere* to
send a `DENY` event or a `HOLD` event today, or invoking the graph on those paths would
error immediately.

The resolution: `interpose.control_plane.agents.stubs.make_stub_node(name)` builds a
placeholder terminal node that does nothing but log that it was reached, then ends the
graph. This means the **routing** to A2/A3/A4 is real, tested, and load-bearing today
— genuinely demonstrating the conditional-edge mechanic this whole exercise is meant
to prove out — while what happens *once you arrive* at those nodes is explicitly not
built yet. That's a narrower, more honest gap than either building fake versions of
three agents that don't do anything real, or delaying the entire graph topology to
Day 8 and losing a day of real LangGraph practice in the meantime.

## Related

- [[23-control-plane-event-bus-and-feature-engineering]]
- [[21-redis-and-the-hitl-hold]]
