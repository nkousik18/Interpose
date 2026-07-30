# aml-investigator

The AML investigation agent (`docs/INTERPOSE_SCOPING.md` Section 9.7, Phase 3 Day 13).
A **client** of Interpose, not part of it -- see
`concepts/30-client-agents-vs-control-plane-agents.md` for why that distinction matters
and how it differs from `src/interpose/control_plane/`'s own, separate LangGraph system.

Given a suspicious-transaction alert, drives a fixed 5-node LangGraph investigation
through the gateway-proxied `ofac-sanctions` and `transaction-graph` MCP servers,
producing a risk assessment, a disposition recommendation, and a narrative report.

## The flow

```
Discovery -> Enrichment -> Assessment -> Recommendation -> Report
```

- **Discovery** -- `get_account`, `query_transactions`, `check_entity` (on the account
  holder), `neighbors` (first hop). No LLM.
- **Enrichment** -- `subgraph` (over the account + its first-hop neighbors),
  `structuring_check`, and (only if Discovery's sanctions check actually cleared the
  match threshold) `get_entity_detail`. No LLM.
- **Assessment** -- the first LLM node: reasons over Discovery + Enrichment's evidence
  to produce a risk level, findings, and rationale. Falls back to a deterministic
  heuristic (sanctions match or structuring signal -> elevated risk) if the LLM call
  fails.
- **Recommendation** -- maps risk level to a disposition (`escalate`/`monitor`/
  `cleared`) and attempts `mark_investigated` -- the HITL trigger point. No AML policy
  pack exists yet (Day 14 adds `aml-write-hitl-gate.yaml`), so this call passes
  through untouched today; no special-casing is needed once a hold *can* happen, since
  the gateway's blocking-hold model just makes the call take longer to return.
- **Report** -- the second LLM node: writes the final narrative and recommended next
  steps. Same fallback discipline as Assessment.

Both LLM nodes reuse `interpose.control_plane.llm.generate_structured` (Groq, strict
JSON schema) rather than a second hand-rolled wrapper -- a deliberate exception to the
zero-`interpose`-dependency rule `mcp-servers/` follows, explained in concept 30.

## Running it

Against a gateway + both MCP servers already running (bare `uv run` loop, or
`docker-compose up`):

```sh
uv run --group agents python agents/aml-investigator/run_investigation.py
```

Picks a real labeled-laundering account from the subsampled dataset as the seed alert
(`aml_investigator.seed.pick_seed_alert`). Pass `--account-id` to investigate a
specific account instead, or `--gateway-url` if the gateway isn't at the default
`http://127.0.0.1:8000`.

Unit tests (pure node logic, fake gateway client, fake LLM -- no network, no API key):

```sh
uv run pytest tests/unit/agents/
```

Integration test through the real gateway and both real MCP servers (fixture data,
still a fake LLM -- `tests/integration/test_investigation_agent.py`):

```sh
uv run pytest tests/integration/test_investigation_agent.py
```

## Named gaps

- **Not wired into the Typer CLI yet.** `interpose demo aml --run` (Section 9.10) is
  Day 15's demo-script work; today this only runs via `run_investigation.py` directly.
- **No AML policy pack yet** (Day 14) -- `mark_investigated` is expected to pass
  through untouched; the HITL hold-and-resume cycle through this specific agent isn't
  exercised until the pack's `aml-write-hitl-gate.yaml` exists.
- **Not deployed into the local `kind` cluster** -- same named gap as
  `mcp-servers/transaction-graph/README.md`; needs `kind.yaml`'s `extraMounts` for the
  real dataset, which isn't added yet.
- **Not run against the real ~150MB subsampled dataset in the automated suite** --
  only fixture data. A manual, live run against the real dataset with a real Groq call
  has been verified (see `docs/project/SESSION_LOG.md`), same division of labor as
  every other day's LLM-calling work.
