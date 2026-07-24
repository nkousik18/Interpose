# Session log

Purpose: a new session (new context window, possibly a new machine) should be able to read this
file and know *exactly* where things stand — not just which phase we're in (`docs/ROADMAP.md`
covers that), but what happened last time, what was decided, and what the immediate next step
is. See `concepts/13-session-continuity-and-progress-logs.md` for why this file exists and how
it fits alongside `CLAUDE.md`, `docs/ROADMAP.md`, and `CHANGELOG.md`.

Newest entry first. One entry per work session (not necessarily per calendar day).

---

## 2026-07-24 — Phase 2 Day 9: Helm chart, first real kind deployment

**What happened:**
- Two upfront scoping calls made explicitly with the user before writing any chart
  code: (1) chart **one** Deployment, matching the real in-process
  gateway+control-plane architecture (Day 7's `run_forever` asyncio task), not the two
  Section 11.5 describes -- charting a second, standalone control-plane Deployment
  would mean it does nothing, since nothing in the code lets it run outside the
  gateway process; (2) build the **MVP slice** of Section 11.4/11.5 for real and name
  the rest (ingress, HPA, RBAC, NetworkPolicy, PodMonitor, Spark CRDs, pod-security
  hardening) as explicit deferred gaps, same pattern as prior days, rather than write
  YAML nothing exercises yet.
- Added real code the chart needed, not just infra: `/healthz` (liveness -- checks
  nothing external, deliberately, so a transient Postgres blip doesn't get a healthy
  gateway pod restarted) and a genuinely-checking `/readyz` (Postgres `SELECT 1` +
  Redis `PING`) on the gateway; `gateway_host`/`gateway_port`/`config_path`/
  `policy_dir` added to `Settings` so the same image/entrypoint works correctly both
  bare (`uv run python -m interpose.gateway`, unchanged default behavior) and
  container-first (Docker image bakes `GATEWAY_HOST=0.0.0.0`, the chart mounts
  ConfigMaps at paths `CONFIG_PATH`/`POLICY_DIR` point to). Two new integration tests.
- Multi-stage `Dockerfile` (`ghcr.io/astral-sh/uv` builder stage, `python:3.12-slim`
  runtime, non-root `uid 10001`, self-contained default `config/` baked in so
  `docker run` works standalone too). Smoke-tested directly against the existing
  docker-compose Postgres/Redis before touching Kubernetes at all.
- Built `charts/interpose/`: Chart.yaml, values.yaml (production-leaning defaults) +
  values-dev.yaml (dev overlay -- chart-created Secret, embedded Postgres/Redis
  already the default), `_helpers.tpl` (naming/labels + the embedded-vs-external
  Postgres/Redis DSN-assembly helpers), Deployment/Service/ConfigMaps/Secret for the
  gateway, first-party (not Bitnami) dev-mode Postgres/Redis Deployments gated by
  `postgres.embedded`/`redis.embedded` -- deliberately not a sub-chart dependency,
  since an external chart-repo dependency buys nothing for a dev-only convenience
  toggle production never uses regardless. Added a `post-install`/`post-upgrade` Helm
  hook Job (`migrate-job.yaml`) running `alembic upgrade head` -- a gap noticed while
  building, not in the original file list: without it, a fresh embedded Postgres pod
  has no schema, and `/readyz` would report healthy (it only checks connectivity) while
  every real audit write 500s.
- Grafana deployed with all four Section 12.4 dashboards (`files/dashboards/*.json`,
  provisioned via ConfigMap + Grafana's file-based dashboard-provider mechanism) --
  Gateway Health, Policy & Governance, AML Pack, Cost Telemetry. Each dashboard's own
  "how to read" text panel states plainly that it's schema-only: no Prometheus is
  deployed by this chart (no PodMonitor either -- named, deferred), and nothing
  exports `/metrics` yet, so every panel query is a provisional metric name, not a
  working query, until Phase 3/4.
- `kind.yaml` (1 control-plane + 2 workers, Section 11.3's shape). `scripts/dev-up.sh`
  (idempotent: reuses an existing cluster, `helm upgrade --install`, backgrounded
  port-forwards for gateway :8000 and Grafana :3000) / `scripts/dev-down.sh` (kills
  the port-forwards, `kind delete cluster`). Deliberately skips cert-manager and
  ingress-nginx, unlike Section 11.3's literal script -- local dev reaches everything
  via `kubectl port-forward`, so there's no TLS/ingress story to stand up yet.
- **Live-tested against a real kind cluster, twice, not just `helm template`.** First
  run surfaced a real bug: the gateway `Service`'s selector matched on
  `app.kubernetes.io/name`/`instance` only, which every workload in the release
  shares (gateway, Postgres, Redis, Grafana) -- so `kubectl port-forward svc/gateway`
  nondeterministically connected to whichever pod the API happened to return (in this
  run, Redis), failing with a confusing "pod does not have a named port 'http'"
  error. Fixed by adding an `app.kubernetes.io/component` label to every
  Deployment/Service selector. Rendering the chart with `helm template` never would
  have caught this -- it doesn't resolve what a selector actually matches at runtime,
  only a real cluster does. Documented as its own section in the new concept file.
- Full clean re-run after the fix: **99s and 110s** (both well under the 5-minute
  target) from `kind create` to all four pods `Running`; `/healthz`/`/readyz` both 200
  through a port-forward (readyz genuinely raced Postgres startup once -- 503 then 200
  a few seconds later, proving the probe logic is real, not a stub); the migration Job
  ran, completed, and deleted itself (`hook-delete-policy`), confirmed via `psql \dt`
  showing `audit_entries` actually exists; all four dashboards visible under the
  "Interpose" folder via Grafana's `/api/search`. `scripts/dev-down.sh` confirmed to
  leave no cluster, no stray port-forward processes, no pidfile.
- Added `helm lint`/`helm template` as a new CI job (Section 11.4's own requirement).
- Added `concepts/26-helm-and-the-interpose-chart.md`: what Helm/a chart/a release
  actually are vs. raw `kubectl apply` or Kustomize, Go templating and
  `_helpers.tpl`, the Service-selector bug as a worked example of what live-cluster
  testing catches that template-rendering can't, the embedded-vs-external toggle
  pattern, and the liveness/readiness/startup probe distinction.
- **159 total tests green** (2 new `/healthz`/`/readyz` integration tests);
  `ruff check .` clean repo-wide; `helm lint`/`helm template` both clean.

**Decisions made:**
- One Deployment for gateway + control-plane, not two -- charts what's real, not what
  Section 11.5 originally pictured. Splitting control-plane into an independently
  scalable service is named v0.2 scope.
- MVP chart scope now, full enterprise scope (ingress/RBAC/NetworkPolicy/PodMonitor/
  Spark CRDs/pod-security hardening) deferred with per-item reasons in
  `charts/interpose/README.md`, not built speculatively.
- First-party dev Postgres/Redis templates, not Bitnami sub-charts -- avoids an
  external chart-repo dependency for a toggle production never exercises anyway.
- A Helm hook migration Job is required infrastructure, not optional polish -- added
  even though it wasn't in the original per-file plan, because without it the chart
  would "deploy successfully" while being silently broken for real audit writes.

**Current state:**
- Phase 2 Day 9 done and checked off. The full stack (gateway+control-plane,
  Postgres, Redis, Grafana) deploys to a real local kind cluster via Helm in under two
  minutes, verified live twice. Day 10 (buffer + integration polish) is what's left
  before Phase 2's gate is fully met -- notably, the HITL cycle and control-plane
  agents have been verified end-to-end via docker-compose (Days 6-8) but not yet
  through the kind-deployed stack specifically, since no MCP upstream server is
  deployed in-cluster yet (nothing to make a real tool call against there until Phase
  3's AML servers, or a demo echo server, land).

**Next steps:**
1. Day 10 — buffer + integration polish: confirm all Week 1 + Week 2 integration
   tests green in CI (not just locally), README quickstart draft, first distributed
   trace visible in Jaeger, adversarial test suite skeleton (fixture generator, no
   attacks yet).
2. Worth deciding early in Day 10: whether to deploy the existing `hello-mcp-http-echo`
   example server in-cluster (via `dev/mcp-servers/`, per Section 11.3 step 5) purely
   to exercise a real end-to-end MCP call through the kind-deployed gateway, or leave
   that gap open until Phase 3's real AML MCP servers arrive -- not yet decided.
3. Commit/push/PR/merge Day 9's work per the established per-day cadence before
   starting Day 10.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented — same
  gap noted at the end of Day 4, still open.
- No automated kind-based deploy test in CI yet (only `helm lint`/`helm template`,
  which don't catch runtime issues like the Service-selector bug this session found
  live) — worth considering for Phase 4 hardening, not required for Day 9's gate.

---

## 2026-07-23 — Phase 2 Day 8: remaining control-plane agents, first real LLM integration

**What happened:**
- First real LLM integration in the project. Provider decision made explicitly with
  the user: **Groq**, not Anthropic, for now -- a genuinely free tier, avoiding
  per-call billing during development. Not a deviation from the scoping doc: Section
  6.4 already names Groq as an anticipated alternative provider behind a
  `Settings.llm_provider`-style swap. Built `interpose.control_plane.llm` as that
  swap seam -- `generate_structured(...)` is the only thing agent code depends on;
  swapping to Claude later touches this one module, not `interpose.control_plane
  .agents.*`.
- Used Groq's real structured-output mode (`response_format={"type": "json_schema",
  ..., "strict": True}`), not looser prompt-and-hope JSON -- matches Section 7's
  "Structured JSON output constrained by Pydantic; no free-form response" literally.
- Built Agent A2 (Anomaly Detector): a live, agent-scoped rate z-score (no
  population baseline store exists, so no cross-agent comparison -- explicitly
  returns `None` rather than a fabricated value below 3 windows of history or when
  history has zero variance) + a repeated-denials rule. Cluster-deviation (the third
  strategy Section 7.8 describes) deferred -- needs Spark-trained K-means centroids
  that don't exist. Optional one-sentence LLM description only on high-severity
  flags.
- Built Agent A4 (Incident Escalator): 3 of 4 Section 7.10 promotion rules
  implemented as a pure, fully-tested `should_promote` function. Extended Day 7's
  graph with a real topology change -- a new `route_after_anomaly_detector` hop so a
  high-severity anomaly from A2 now continues on to A4 (previously A2 only ever
  ended the graph). The fourth rule (risk > 0.8 with pending HITL, via A3) is real in
  the logic but not yet reachable via the graph -- named explicitly as a deliberate
  gap, not a silent omission.
- **Found and fixed a real severity bug via the integration tests** (not the LLM):
  `should_promote` checks repeated-denials before anomaly-severity, so an event
  tripping both got under-reported as `med` severity based purely on which string
  came back first. Fixed with a separately-tested `compute_incident_severity` that
  checks for a co-occurring high-severity anomaly independent of which rule
  technically matched.
- Built Agent A3 (Evidence Composer): real evidence assembly (last 20 session calls,
  matched policy rules, A1's risk components, and a same-agent+same-tool prior-HITL-
  outcome count as an honestly-simplified stand-in for the doc's "similar patterns").
  Always has `state.enriched` populated (routing guarantees `HOLD` goes through A1
  first) -- raises loudly if that invariant is ever violated rather than silently
  composing an incomplete packet.
- **Fixed a real design gap discovered while building A3**: `HITLPacket.ticket_id`
  needs to be the actual Redis ticket ID, but the gateway was publishing the
  `DecisionEvent` *before* the ticket existed. Reordered `_handle_hold` (create the
  ticket, then publish, now carrying `hitl_ticket_id`) and added that field to
  `DecisionEvent` -- a small, surgical fix rather than a documented gap, since the
  correct fix was cheap once noticed.
- **Two real bugs found only by an actual live Groq API call**, neither catchable by
  mocked unit tests: (1) Groq's strict schema mode requires
  `additionalProperties: false` on every object, which Pydantic doesn't set by
  default -- fixed centrally in the LLM wrapper (`_strict_schema`), covered by a
  permanent regression test. (2) `openai/gpt-oss-20b` (the configured model) spends
  part of its token budget on hidden reasoning before producing visible output; at
  default effort, a longer prompt (Agent A4's 5-8 sentence narrative) exhausted the
  budget before emitting any JSON at all -- fixed with `reasoning_effort="low"`.
- **Found and fixed a test-determinism hazard the moment a real API key existed**:
  once the user added a real `GROQ_API_KEY` to their local `.env` for the smoke test,
  every "fallback path" integration test silently started calling the real API
  instead. Added `tests/conftest.py` forcing `GROQ_API_KEY=""` for the whole
  automated test session, unconditionally -- the suite's behavior no longer depends
  on what happens to be in any developer's local environment.
- Rewrote `tests/integration/test_control_plane_graph.py`'s fixtures with care to
  produce clean, non-cascading test cases (e.g. exactly 2 denials to cross Agent A1's
  risk threshold without also tripping Agent A2's own repeated-denials threshold),
  plus dedicated cascade tests for the new A2→A4 path.
- Added `concepts/24-narrative-generation-with-a-real-llm.md` and
  `concepts/25-remaining-control-plane-agents.md`.
- **154 total tests green** (61 new control-plane unit tests, graph integration
  tests rewritten and expanded); `ruff check .` clean repo-wide.

**Decisions made:**
- Groq over Anthropic for now, explicitly at the user's request, for cost reasons --
  not a scope reduction, since it's the same provider-swappable design the doc
  already called for.
- `reasoning_effort="low"` and `max_tokens=500` as defaults for all structured LLM
  calls in this project -- these are short, low-ambiguity tasks that don't benefit
  from deep reasoning, and the token budget needs to go to the actual output.
- Automated tests must never depend on local secrets, enforced via `tests/conftest.py`
  rather than relying on discipline alone.

**Current state:**
- All five control-plane agents are real. Phase 2 is not yet complete -- Day 9
  (Helm chart + `kind` deployment) and Day 10 (buffer/integration polish) remain
  before the phase gate is met.

**Next steps:**
1. Day 9 — Helm chart + `kind` deployment: chart templates (Section 11.4), a dev
   values file with embedded Postgres/Redis sub-charts, `scripts/dev-up.sh`
   completing kind-create + helm-install + port-forwards in under 5 minutes, Grafana
   dashboard schemas (data comes later, Phase 3). First real Kubernetes deployment
   of Interpose -- introduce Helm as a concept when this starts (Kubernetes and
   Terraform are already covered from Phase 0; Helm itself isn't yet).
2. Day 10 — buffer + integration polish: all tests green in CI, README/quickstart
   draft, first distributed trace in Jaeger, adversarial test suite skeleton.
3. Commit/push/PR/merge Day 8's work per the established per-day cadence before
   starting Day 9.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented — same
  gap noted at the end of Day 4, still open.
- The user's real `GROQ_API_KEY` now lives in a local, gitignored `.env` -- confirm
  `.gitignore` actually excludes it before the next commit (it should already, per
  the Day 0 `.gitignore` setup, but worth a explicit check given this is the first
  time a real secret has actually been placed in that file).

---

## 2026-07-22 (cont'd, 5) — Phase 2 Day 7: LangGraph control-plane skeleton

**What happened:**
- First LangGraph work in the project. Added `langgraph` as a dependency and
  explored its actual API (a `StateGraph` over a typed state, nodes as plain
  functions, conditional edges via router functions, `.compile()` then `.ainvoke()`/
  `.astream()`) before writing any control-plane code, since this is one of the
  three resume-gap technologies the whole project exists to demonstrate real
  competence in, not just import.
- Added `interpose.control_plane.state`: the full typed state model from Section 7.4
  (`DecisionEvent`, `EnrichedDecision`, `AnomalyFlag`, `HITLPacket`, `Incident`,
  `InterposeState`) -- defined as one complete contract now even though only two of
  five agents exist yet, since it's a single design decision, not five incremental
  ones.
- Added `interpose.control_plane.bus.EventBus` -- the exact module/class path
  Section 6.17 names as "the documented seam" for swapping in-process pub/sub for
  Redis Streams later. An `asyncio.Queue` wrapper; publishing is a fast, non-blocking
  handoff so control-plane processing never slows the gateway's hot path (Section
  7.12).
- Built Agent A0 (Supervisor, `interpose.control_plane.agents.supervisor`): pure
  rule-based dispatch, no LLM, as two sequential conditional-edge functions rather
  than one. **Deliberate judgment call:** Section 7.5's ASCII diagram reads like a
  parallel fan-out to three specialists at once; Section 7.6's prose describes a
  conditional sequential path (`DENY` skips straight to A4; everything else goes
  through A1 first, then conditionally to A2 or A3). Went with the prose -- more
  specific than a diagram, and matches how a supervisor/dispatcher pattern is
  normally understood. 20+ case test matrix per Section 7.6's own testing spec.
- Built Agent A1 (Policy Evaluator, `interpose.control_plane.agents.policy_evaluator`):
  computes real session features live from `audit_entries` (calls/minute, unique
  tools, total calls, HITL ticket count, denial count) rather than the "materialized
  view refreshed every 15 minutes" the doc describes -- that's a Spark job that
  doesn't exist; a live query is simpler and sufficient today. Three of Section 7.7's
  listed features deliberately not computed, each missing a named, concrete
  dependency (read/write ratio needs a tool-action registry; sanctions-check
  frequency needs the OFAC MCP server, Phase 3; per-tool z-scores need the same
  missing historical-baseline store as the materialized view). Zero LLM calls --
  Section 7.7 gates the narrative LLM call on a HITL packet being composed
  downstream (Agent A3, Day 8), so none of that applies yet.
- The risk-score formula is an explicit, hand-weighted heuristic, documented as such
  (not a calibrated model -- no production data yet to calibrate against). Its output
  now gets written into `interpose:session:{session_id}` in Redis -- the first real
  reader/writer of the session-state hash deferred twice already (Days 5 and 6).
- Agents A2 (Anomaly Detector), A3 (Evidence Composer), A4 (Incident Escalator) are
  placeholder stub terminal nodes (`interpose.control_plane.agents.stubs`) -- the
  Supervisor's routing *to* them is real and tested; what happens once execution
  arrives is not, until Day 8.
- Wired it all into the gateway: `_publish_decision_event` publishes a `DecisionEvent`
  after each decision-defining audit write (`DENIED`, `HELD`, `INTENT` -- never the
  `COMPLETED`/`UPSTREAM_ERROR` follow-ups, since the decision itself was already
  published). A background `asyncio.Task` (`interpose.control_plane.runner.run_forever`)
  consumes the bus and runs the graph, started at gateway startup and cancelled at
  shutdown.
- Verified two ways: (1) the graph directly against real Postgres, checking both
  routing (`astream`'s node sequence) and A1's actual enrichment content across
  PASS/HOLD/DENY/elevated-risk-PASS paths (`tests/integration/test_control_plane_graph.py`);
  (2) the full gateway wiring, by making a real HTTP call and polling Redis for A1's
  risk-score hash to appear (`tests/integration/test_gateway_control_plane.py`) --
  proof "decisions flow from gateway to control plane" end to end, not just that the
  pieces compile.
- Learned a real LangGraph quirk worth remembering: node inputs/outputs are plain
  dicts internally, but a nested Pydantic field on the final `.ainvoke()` result comes
  back as an actual model instance, not a re-serialized dict -- attribute access, not
  another `[...]` lookup. Tripped up the first draft of the graph-level tests.
- Added `concepts/22-langgraph-fundamentals-and-supervisor-routing.md` and
  `concepts/23-control-plane-event-bus-and-feature-engineering.md`.
- **120 total tests green** (34 new control-plane unit tests, 5 new integration
  tests); `ruff check .` clean repo-wide.

**Decisions made:**
- Supervisor routing follows Section 7.6's prose (sequential conditional dispatch),
  not Section 7.5's diagram (which reads as parallel fan-out) -- see concept 22.
- Stub terminal nodes for A2/A3/A4 rather than either faking their behavior or
  delaying the whole graph topology to Day 8 -- the routing edges are real today.
- A1's risk score is a named, deliberate heuristic, not a stand-in for A2's later,
  more principled (Spark/K-means-based) anomaly detection -- different purposes.

**Current state:**
- Phase 2 Day 7 done and checked off. Decisions genuinely flow from the gateway into
  a real, tested LangGraph graph; two of five agents do real work, three are honest
  placeholders with real routing already wired to them.

**Next steps:**
1. Day 8 — remaining control-plane agents: Anomaly Detector (A2), Evidence Composer
   (A3), Incident Escalator (A4). First LLM integration in the project (Claude via
   API) for narrative-producing agents, with structured Pydantic output enforcement
   and snapshot/golden-fixture testing for the LLM outputs. This will need an
   Anthropic API key configured -- first time the project actually calls an LLM.
2. Commit/push/PR/merge Day 7's work per the established per-day cadence before
   starting Day 8.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented — same
  gap noted at the end of Day 4, still open.

---

## 2026-07-22 (cont'd, 4) — Phase 2 Day 6: Redis, HITL hold, `interpose review`

**What happened:**
- Merged Phase 1 (Days 1-5, plus the Phase 0 remainder) to `main` via PR #2 first --
  squash-merged after `lint`/`test` both passed on CI. Established a new working
  convention per explicit user request: commit → push → PR → wait for CI → merge
  after *every* day's work from here on, not just at phase boundaries. Saved as a
  standing feedback memory (`feedback_git_workflow_per_day`).
- Added Redis to `docker-compose.yaml` (port 6379, default -- nothing else on this
  machine was using it) and the `redis` Python client. Added `redis_url` to
  `interpose.config.Settings`.
- Built `src/interpose/session/`: `redis_client.py` (sync + async connection
  factories, same split as `interpose.audit`'s engine setup) and `hitl.py` (the ticket
  queue -- `interpose:hitl:{ticket_id}` hash with TTL, `interpose:hitl:pending` set for
  fast listing, `create_ticket`/`get_ticket`/`wait_for_decision` async for the gateway,
  `list_pending`/`decide_ticket` sync for the CLI).
- `hitl_gate` now evaluates for real in `interpose.policies.policyset`: added
  `Outcome.HOLD` and `reviewer_group`/`timeout_seconds` fields on `PolicyDecision`,
  replacing the `NotImplementedError` stub from Day 3. Updated/added unit tests
  accordingly (51 policy tests now, from 49).
- Wired the HOLD path into the gateway (`interpose.gateway.app`): writes a `HELD`
  audit row, opens a Redis ticket, then `await`s `wait_for_decision` (polling every
  250ms) up to the policy's timeout. Approved → forwards for real, linked to the
  `HELD` row via `parent_id` exactly like a `PASS`. Denied or timed-out → a
  structured JSON-RPC error (`hitl_denied` / `hitl_timeout`, new error codes -32003/
  -32004), also linked via `parent_id`. Refactored the PASS-path forward+audit logic
  into a shared `_forward_and_record` helper since an approved hold needs the exact
  same forward-then-record behavior a plain PASS does.
- **Deliberate design call, written into the code and a new concept doc:** the
  scoping doc's Stage 7 wording ("returns a held response... immediately... HITL flow
  takes over") reads as an async retry/resume model, but MCP's `tools/call` has no
  built-in mechanism for that. Built a blocking (async, non-blocking for *other*
  requests) wait on the same request instead -- simpler, honestly testable in one
  `asyncio.gather` per test, at the cost of holding an HTTP connection open for up to
  the full `timeout_seconds` (documented as a known tradeoff, not glossed over).
- Built `interpose review list/approve/deny` (`src/interpose/cli/main.py`), backed by
  the same sync Redis client used elsewhere. `decide_ticket` returns `(ticket, applied)`
  so the CLI can distinguish "you just decided this" from "already settled by someone
  else" (idempotent, doesn't silently overwrite who actually decided first).
- Added two new test tools (`hitl_tool`, `hitl_timeout_tool`) and matching policies
  (30s and 2s timeouts) to exercise approve/deny/timeout without slowing the suite
  down waiting on a real hour-long window.
- Verified the full cycle live against real Postgres + Redis
  (`tests/integration/test_gateway_hitl.py`): approve → forwards, with
  `hitl_reviewer`/`hitl_decision`/`hitl_rationale` populated on the `COMPLETED` row;
  deny → never forwards; no reviewer within the window → times out and denies. All
  three produce a correctly linked, hash-chain-verifying `HELD` → terminal-row pair.
- Extended the shared `clean_state` fixture (renamed from `clean_audit_table`) to also
  flush Redis between tests, since a leftover ticket could otherwise be picked up by
  another test's "first pending ticket" logic.
- Added `concepts/21-redis-and-the-hitl-hold.md`.
- **81 total tests green**; `ruff check .` clean repo-wide.

**Decisions made:**
- Block-and-poll (async) for the HITL hold, not an immediate-response-plus-retry
  model -- see above and concept 21 for the full reasoning.
- Session-state hash (`interpose:session:{agent_id}`, Section 6.8) deliberately not
  built yet -- nothing reads/writes a risk score until Day 8's anomaly detector.
- Git workflow going forward: commit/push/PR/merge after each day, not batched.

**Current state:**
- Phase 2 Day 6 done and checked off. HITL approval/denial/timeout all work
  end-to-end against real infrastructure, with a complete, verifiable audit trail.

**Next steps:**
1. Day 7 — Control-plane LangGraph skeleton: typed state models
   (`InterposeState`, `DecisionEvent`), Supervisor (A0) and Policy Evaluator (A1)
   agents, in-process pub/sub event bus. This is the first LangGraph work in the
   project -- introduce it as a concept when it starts.
2. Commit/push/PR/merge Day 6's work per the new per-day cadence before starting Day 7.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented — same
  gap noted at the end of Day 4, still open.

---

## 2026-07-22 (cont'd, 3) — Phase 1 Day 5: end-to-end tests, verify-audit CLI — Phase 1 complete

**What happened:**
- Closed the "5+ end-to-end tests" checklist (scoping doc Section 14.5 Day 5): added
  the two missing paths, **rate-limit** (new `throttled_tool` +
  `config/policies/hello-echo-throttle.yaml`, limit=1/window=60s — second call within
  the window denied with reason `rate_limit_exceeded`) and **malformed request**
  (garbage bytes to `/mcp/hello-echo` → HTTP 400,
  `tests/integration/test_gateway_edge_cases.py`). Happy path, deny path, and unknown
  server were already covered from Days 1/3/4.
- Built `interpose verify-audit` (`src/interpose/cli/main.py`, Typer — already a
  transitive dependency via `mcp[cli]`, so no new package needed). Added a
  `[project.scripts]` entry point so `interpose` is a real installed command.
- Hit and documented a real Typer gotcha: with only one command registered, Typer
  silently collapses the CLI into a flat form (`interpose --since ...`) instead of
  the documented `interpose verify-audit --since ...` shape. Fixed with an empty
  `@app.callback()`, which signals "this is a command group" regardless of how many
  commands currently exist — relevant again once `interpose review` lands in Phase 2.
- Deliberate design decision for `--since`: it only changes what's *reported*, never
  what's *verified* — the CLI always walks the whole chain from genesis regardless of
  the filter, because a hash chain's guarantee doesn't hold for an arbitrary slice
  checked in isolation (see concept 19). Written into the command's own `--help` text,
  not just code comments.
- Tested the CLI against a real Postgres (`tests/integration/test_verify_audit_cli.py`,
  via `typer.testing.CliRunner`): empty log, valid chain, and a genuine tamper-and-fail
  run — the last one proves the CLI itself catches tampering, not just `chain.py` in
  isolation as Day 4 already showed.
- Moved the `clean_audit_table` fixture (originally local to Day 4's test file) into
  `tests/integration/conftest.py` as `autouse=True`, now that a second test file needs
  the same clean-slate-per-test guarantee.
- Fixed CI's Postgres migration path for real: dropped and recreated
  `audit_entries`/`alembic_version` locally and re-ran `alembic upgrade head` from
  scratch to confirm the exact sequence CI runs against an ephemeral database works
  cleanly, not just against the already-migrated dev database.
- **Resolved a loose end flagged at the end of Day 4:** `docs/ROADMAP.md`'s Phase 1
  gate said "a LangGraph agent makes a tool call through Interpose" — corrected to
  match what the scoping doc's actual Section 14.5 EOW1 gate says (no LangGraph
  mention at all; that's Phase 2, Section 14.6). Left a note in the roadmap explaining
  the correction rather than silently editing it.
- **Two Day 5 checklist items deliberately not done, with reasons written into
  `docs/ROADMAP.md`:** Redis joining `docker-compose.yaml` (nothing consumes it yet —
  rate limiting is still Day 2's in-memory stand-in; adding it now would be unused
  infrastructure until Day 6's HITL work needs it) and containerizing the gateway +
  mock upstream for a fuller docker-compose stack (deferred to Phase 2 Day 9, where a
  container image is actually load-bearing for the Helm chart, rather than building
  one twice).
- Added `concepts/20-cli-with-typer.md`.
- **76 total tests green**; `ruff check .` clean repo-wide.

**Decisions made:**
- `--since` on `verify-audit` is report-scoping only, never verification-scoping (see
  above and concept 20) — a deliberate, documented choice, not an oversight.
- Redis and gateway/upstream containerization both deferred with explicit written
  reasons rather than silently dropped from the day's scope.

**Current state:**
- **Phase 1 (Foundation) is complete.** The gateway proxies real MCP traffic, governs
  it via policy (allow/deny/rate-limit all verified live), and durably records every
  decision in a verifiable, hash-chained Postgres log — with a CLI to check that
  verification independent of the test suite. 76 tests green, CI passing the same
  Postgres-backed suite.

**Next steps:**
1. Move into Phase 2 (Governance): Day 6 — Redis joins for real (session state + HITL
   ticket queue), the HITL policy handler (creates a ticket, holds the call, returns a
   held response), and the `interpose review` CLI command (list pending tickets,
   approve/deny with rationale). This is also where `hitl_gate`'s current
   `NotImplementedError` stub (Day 3) gets real behavior.
2. Introduce Redis as a concept when Day 6 starts (first real use of it in the
   project, after being named but deferred twice now).

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented — same
  gap noted at the end of Day 4, still open.
- **Nothing in this repo has been committed to git yet across Days 1-5 of this
  session** — all work exists only in the working tree. Not a blocker (never asked
  to commit), but worth doing consciously rather than letting it keep growing.

---

## 2026-07-22 (cont'd, 2) — Phase 1 Day 4: Postgres audit log, hash chain, wired in

**What happened:**
- Added a real Postgres dependency: `docker-compose.yaml` (single `postgres:16`
  service, host port **5433** rather than 5432 -- this machine already has an
  unrelated PostgreSQL 18 install running natively on 5432, left untouched rather
  than fought with).
- Added `src/interpose/config.py`: first real `pydantic-settings` `Settings` object
  (just `database_url` for now, from env/`.env`), shared by both the app and Alembic
  so there's one source of truth for the connection string. `.env.example` added.
- Added `src/interpose/audit/models.py`: SQLAlchemy 2.x `AuditEntry` matching the
  scoping doc's Section 6.7 schema exactly (status enum, hash-chain columns,
  self-referential `parent_id` FK, three indexes).
- Initialized Alembic (`alembic/`), wired `env.py` to read the DB URL from
  `interpose.config` and target `AuditEntry`'s metadata, autogenerated and applied the
  first migration against the real local Postgres. Verified the resulting schema
  matches spec via `psql \d audit_entries`.
- Added `src/interpose/audit/chain.py`: the hash-chain implementation (`this_hash =
  SHA256(prev_hash || canonical_json(entry))`, genesis hash, `verify_chain` that walks
  entries and reports the first mismatch). Deliberately excludes the DB `id` from the
  hashed payload (storage detail, not semantic content). 12 unit tests, pure logic, no
  DB needed -- including three that simulate tampering and confirm detection.
- Added `src/interpose/audit/store.py` (`AuditStore.write_entry`) and
  `src/interpose/audit/db.py` (async engine/session setup). Writers serialize via a
  Postgres advisory lock (`pg_advisory_xact_lock`) scoped to the whole chain, since
  concurrent writers naively reading "the latest hash" could both build on the same
  `prev_hash` and corrupt the chain.
- Wired Stage 6 and Stage 8 into `src/interpose/gateway/app.py`: every `tools/call`
  request now produces either one `DENIED` row (policy denial -- nothing was ever
  pending) or a linked `INTENT` → `COMPLETED`/`UPSTREAM_ERROR` pair (`parent_id`),
  matching the append-only design (no row is ever updated in place). Non-tool-call
  traffic still bypasses audit entirely, same reasoning as Day 3's policy scoping.
  `UPSTREAM_ERROR` (a real httpx failure talking to the upstream) returns a structured
  JSON-RPC error to the agent, same pattern as a policy denial.
- A real, deliberate MVP simplification, written down rather than left implicit: the
  hash needs every field's value *before* insert, but Section 6.7 wants Postgres's own
  server time as the authoritative timestamp -- which isn't known until *after*
  insert, and can't be fixed up afterward without an UPDATE the append-only design
  rules out. Used the application's own clock instead; the scoping doc already flags
  real timestamp signing as v0.2 scope, so this is the same tradeoff made now.
- Updated CI (`.github/workflows/ci.yml`) with a Postgres service container and an
  `alembic upgrade head` step -- without this the new integration tests would have
  broken the pipeline immediately, so this couldn't wait for Day 5 as originally
  planned.
- Added `concepts/18-postgres-sqlalchemy-alembic.md` (the tooling: why a real
  database now, what an ORM buys you, migrations as a paper trail) and
  `concepts/19-hash-chained-audit-log.md` (the domain concept: tamper-evidence, the
  two-row append-only design, the advisory-lock race, the timestamp tradeoff).
- 69 total tests green (12 new hash-chain unit tests + 3 new live-Postgres
  integration tests); `ruff check .` clean repo-wide (added `alembic/versions/` to
  ruff's `extend-exclude` -- autogenerated migrations aren't worth hand-formatting).

**Decisions made:**
- Postgres runs on host port 5433 for this project, not the Postgres default 5432 --
  a pre-existing, unrelated native Postgres 18 install already owns 5432 on this
  machine and was left alone.
- Timestamp hashed/stored is the application's clock, not Postgres's server time,
  as a named MVP simplification (see concept 19) -- not silently assumed.
- CI's Postgres service was added today (originally slated for Day 5) because Day 4's
  own tests need it to pass; deferring would leave `main`'s CI broken in the interim.

**Current state:**
- Phase 1 Day 4 done and checked off. The gateway now proxies, governs, *and*
  durably records every tool call it sees, with a verifiable integrity guarantee.

**Next steps:**
1. Day 5 (buffer + integration polish, per scoping doc Section 14.5): fuller
   docker-compose (gateway + mock upstream joining Postgres, Redis arriving when HITL
   needs it in Day 6, not before), 5+ end-to-end tests (happy/deny/rate-limit/
   malformed/unknown-server paths), `interpose verify-audit` CLI, confirm CI green.
2. **Loose end to resolve, not yet fixed:** `docs/ROADMAP.md`'s Phase 1 "Gate" text
   says "a LangGraph agent makes a tool call through Interpose" -- but LangGraph isn't
   introduced until Phase 2 (control-plane agents) per the scoping doc's own Section
   14.6. This looks like an artifact from the first session's adaptation of Section 14,
   not a deliberate design call. Worth reconciling wording with the user before
   treating Phase 1's gate as satisfied on a technicality.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.
- Postgres append-only enforcement at the role level (writer = INSERT only, no
  UPDATE/DELETE grant -- Section 10.7) is described in the scoping doc but not yet
  implemented; today's tamper-detection test proves the hash chain *notices* an
  UPDATE, not that one is prevented. Worth doing before this is called production-grade.

---

## 2026-07-22 (cont'd) — Phase 1 Day 3: policy engine wired into the gateway

**What happened:**
- Wired Stages 4-5 of the request lifecycle into `src/interpose/gateway/app.py`:
  every `tools/call` request now gets its tool name extracted and run through
  `PolicyEngine.compile(server, tool).evaluate(...)`. `PASS` forwards as before;
  `DENY` short-circuits and returns a structured response — the upstream is never
  called. Everything else (`initialize`, `list_tools`, notifications, the long-lived
  GET stream) still bypasses policy entirely, since there's no `{server, tool}` pair
  to evaluate a policy against outside an actual tool call.
- Denials come back as a JSON-RPC error object (HTTP 200, `error.code = -32001` in
  the implementation-defined server-error range), not an HTTP 4xx — matching what the
  MCP SDK's `ClientSession` already expects and raises `McpError` from automatically.
- Implemented Section 6.5's fail-closed rule literally: any exception raised during
  policy compilation/evaluation (including the two stub effect types' deliberate
  `NotImplementedError`) becomes a DENY with reason `policy_engine_error`, logged in
  full via `logger.exception` — never a silent pass-through.
- Added `PiiRedactionEffect` and `HitlGateEffect` to `schema.py` (all 5 documented
  effect types now parse) and made `PolicySet.evaluate` raise `NotImplementedError`
  loudly if either shows up in an applicable policy set, rather than silently
  skipping them as if unconfigured.
- Added `config/policies/hello-echo-denylist.yaml` (denylists a new `dangerous_tool`
  test tool on the `hello-echo` upstream; `echo` stays default-allow) and a matching
  `dangerous_tool` in `examples/hello-mcp-http-echo/server.py`, purely so there'd be
  a real PASS/DENY contrast to test against.
- Extracted the subprocess-fixture (gateway + upstream server, both real processes on
  real ports) from Day 1's test into `tests/integration/conftest.py`, now shared by
  `test_gateway_naive_forward.py` and the new `test_gateway_policy.py`.
- 9 new unit tests (schema parsing + evaluate-raises for the two stub types) bring
  the policy suite to 49; full suite is 54 tests, all green, `ruff check` clean.
- Added `concepts/17-fail-closed-policy-enforcement.md`: why a denial is a JSON-RPC
  error rather than an HTTP error, what fail-closed actually means operationally
  (not just "add a try/except"), and the tools/call-only scope of policy enforcement.

**Decisions made:**
- Local dev policy source is `config/policies/` (a directory of YAML files loaded at
  startup), parallel to Day 1's `config/upstreams.yaml` — both are local stand-ins for
  what become Kubernetes ConfigMaps in Phase 2, not previews of the AML-specific
  `policies/packs/aml/` (which stays empty until Phase 3).
- Policy denial responses are JSON-RPC-level (200 + error object), not HTTP-level,
  because a denied tool call is a valid MCP exchange the gateway chose not to forward
  — not a malformed request or a routing failure.

**Current state:**
- Phase 1 Day 3 done and checked off. The gateway now genuinely governs tool calls,
  not just proxies them — but there's still no persistent audit trail; every decision
  only exists in process logs until Day 4.

**Next steps:**
1. Day 4 — Postgres + audit log skeleton: schema per Section 6.7 (Alembic migration),
   SQLAlchemy models (`interpose.audit.models`), hash chain implementation
   (`interpose.audit.chain`) with its own unit tests, Stage 6 (pre-forward intent
   write) and Stage 8 (completion write) wired into the gateway.
2. Test target for Day 4: one end-to-end call produces two linked audit entries and
   the hash chain verifies.
3. Introduce Postgres + SQLAlchemy + Alembic as concepts when Day 4 starts — first
   real stateful dependency beyond in-memory/file-based state so far.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.

---

## 2026-07-22 — Phase 1 Day 2: policy engine skeleton

**What happened:**
- Built `src/interpose/policies/`: `schema.py` (Pydantic policy models — `Policy`,
  `AppliesTo`, and a discriminated-union `Effect` covering `allowlist`, `denylist`,
  `rate_limit`), `loader.py` (YAML → `Policy`, directory loading with duplicate-name
  rejection), and `policyset.py` (`PolicySet` + `PolicyEngine`, the in-memory
  compiled-and-cached lookup Stage 4 calls for, plus a `RateLimiter`).
- Implemented and tested a specific, non-obvious semantic: an `allowlist` policy on a
  server flips that *whole server* to default-deny, not just its own tool — mirrors
  how AWS security groups / K8s `NetworkPolicy` allow-rules work. Documented in both
  the code (`policyset.py` module docstring) and
  `concepts/16-policy-engine-composition.md`.
- `RateLimiter` is in-memory and per-process for now — deliberately temporary, sharing
  its `check_and_increment` interface with the Redis-backed version Section 6.8
  specifies, so the swap later doesn't touch policy-evaluation code. Made it
  clock-injectable specifically so window-expiry could be unit-tested without a real
  `time.sleep`.
- Wrote 40 unit tests across `tests/unit/policies/{test_schema,test_loader,
  test_policyset}.py` (target was 20+): schema validation and defaults, YAML loading
  and duplicate-name rejection, and policy composition (allowlist/denylist/rate-limit
  interaction, evaluation ordering, compilation caching). All passing; `ruff check`
  clean; full suite (43 tests total, including Day 1's integration tests) green.
- Added `concepts/16-policy-engine-composition.md`: why a YAML DSL over hardcoded
  Python, Pydantic discriminated unions as the underlying technique, the allowlist
  semantics, hot-reload-ready compilation (rebuild + atomic swap, no reload trigger
  wired yet), and the Redis rate-limit seam.

**Decisions made:**
- Only 3 of the eventual 5 effect types built now (allowlist, denylist, rate_limit);
  PII redaction and HITL gate are Day 3's job, once the gateway has policy evaluation
  wired in and somewhere to route a held call. Deliberately not built ahead of that.
- `PolicyEngine` is immutable once constructed — a config reload means building a new
  one and swapping the reference, never mutating an existing one in place.

**Current state:**
- Phase 1 Day 2 done and checked off. Policy models, loading, and in-memory
  compiled evaluation all exist and are tested — but nothing in the gateway calls any
  of this yet. The gateway from Day 1 is still a fully naive forward.

**Next steps:**
1. Day 3 — wire the policy engine into the gateway: Stage 4 (compile) and Stage 5
   (evaluate) plugged into the `/mcp/{server_name}` request lifecycle, with `PASS`
   forwarding to upstream and `DENY` returning a structured error to the agent. Add
   stub effect types for PII redaction and HITL gate (schema only, no real behavior)
   so all 5 documented types at least parse.
2. Test target for Day 3 (per scoping doc Section 14.5): a real agent call that a
   policy actually fires on, both the `PASS` and `DENY` paths exercised through the
   live gateway (extending `tests/integration/`).

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.

---

## 2026-07-21 (cont'd) — Phase 1 Day 1: gateway naive-forward proxy

**What happened:**
- Built the first real slice of the gateway (`src/interpose/gateway/`): a FastAPI app
  implementing Stages 1-3 of the request lifecycle (scoping doc Section 6.5) — ingress
  (request ID, correlation ID, agent ID from a bearer token if present), parse (MCP
  SDK's `JSONRPCMessage`, malformed bodies rejected with 400), and route resolution
  (`config/upstreams.yaml`, a local stand-in for the Kubernetes ConfigMap that'll exist
  once Helm does) — then jumps straight to a naive forward (Stages 7-9), skipping
  policy compilation/evaluation and audit writes (Stages 4-6) entirely for now.
- Forwarding streams the response chunk-by-chunk via `httpx` + FastAPI's
  `StreamingResponse`, rather than buffering it — necessary because the streamable-HTTP
  transport opens a long-lived GET connection for server-initiated messages, which
  never "completes" the way a buffered request/response would expect.
- Added `examples/hello-mcp-http-echo/`: the same `echo` tool as the existing stdio
  example, but served over streamable-HTTP — the transport the gateway actually
  proxies in production (Section 6.17), unlike the earlier stdio demo.
- Added `tests/integration/test_gateway_naive_forward.py`: runs the gateway and the
  echo server as two real subprocesses on real ports, drives a genuine MCP client
  through the gateway (`initialize` → `list_tools` → `call_tool`), and checks a 404 on
  an unrouted server name. Deliberately not using FastAPI's in-process test client,
  since the long-lived GET-stream behavior only surfaces against a live server.
  Debugged one real issue along the way: a stray gateway subprocess from an earlier
  fixture teardown was left holding port 8000 (graceful `terminate()` alone isn't
  reliable within a short timeout) — fixed by falling back to `kill()` on timeout.
- Added `fastapi`, `uvicorn[standard]`, `pyyaml` as core dependencies and
  `pytest-asyncio` as dev; both tests green, `ruff check` clean.
- Added `concepts/15-fastapi-and-the-naive-proxy.md`: what FastAPI is and why it was
  chosen, what the naive proxy actually does today vs. Section 6.5's full 9 stages,
  why streaming (not buffering) is required, and ConfigMap-driven routing before a
  real ConfigMap exists.

**Decisions made:**
- Route table (`config/upstreams.yaml`) is a flat `{name: {url}}` YAML map, loaded
  once at startup; this is intentionally the simplest thing that satisfies "ConfigMap-
  driven" for local dev, not a preview of the eventual Helm-templated shape.
- Integration tests for the gateway spin up real subprocesses on real ports rather than
  using ASGI in-process test clients, specifically because streamable-HTTP's
  long-lived GET stream needs a live server to exercise honestly.

**Current state:**
- Phase 1 Day 1 (per `docs/ROADMAP.md`'s adaptation of scoping doc Section 14.5) is
  done and checked off. The gateway proxies real MCP traffic with no policy or audit
  involved yet — purely transparent forwarding.

**Next steps:**
1. Day 2 — policy engine skeleton: Pydantic policy models
   (`interpose.policies.schema`), YAML loading + validation (`interpose.policies.loader`),
   three initial policy types (allowlist, denylist, rate limit), in-memory `PolicySet`
   compilation, 20+ unit tests.
2. Day 3 — wire the policy engine into the gateway (Stages 4-5 of the lifecycle).
3. Introduce Pydantic-as-a-DSL-validator as a concept when Day 2 starts (already used
   informally; Day 2 is the first time it's load-bearing for policy correctness).

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.

---

## 2026-07-21 — Spark/PySpark set up; IBM AML dataset subsampled; Phase 0 complete

**What happened:**
- Installed OpenJDK 17 via Homebrew (keg-only, alongside an existing but too-new
  OpenJDK 25) after confirming Spark needs a JVM it's actually tested against.
  Added `pyspark>=4.2.0` as a dedicated `analytics` dependency group in
  `pyproject.toml` (not the default install — only the Spark jobs need it).
- Added `src/interpose/analytics/spark_env.py::ensure_java_home()` so every Spark job
  points at the right JDK automatically; verified with a real local `SparkSession`
  smoke test.
- Wrote and ran `src/interpose/analytics/subsample_aml.py`, the IBM AML dataset
  subsampling job (scoping doc Section 10.3), against the full 31.9M-row HI-Medium
  CSV in `local[*]` mode (~3.5 min on this laptop). Result: 500,000 accounts,
  3,158,483 transactions, all 35,230 labeled laundering transactions retained, 100/100
  sampled laundering patterns (across all 7 typologies) verified fully connected.
  Output written as Parquet to `~/.interpose/data/ibm-aml/{transactions,accounts}/`.
- Deviated deliberately from the scoping doc's literal sampling procedure (pure
  uniform random account selection): guaranteed every laundering-labeled account's
  inclusion first, then filled the rest of the 500K target with a seeded uniform
  random draw. Pure uniform sampling would very likely have broken pattern
  connectivity by chance, given how few accounts (41,857) touch any labeled
  laundering transaction out of the ~2.08M-account universe.
- Found and documented a third scoping-doc inaccuracy in `data/README.md` (alongside
  the two from 2026-07-20): the doc predicted ~8-12M transactions would survive
  subsampling; actual measured result is 3.16M. Also noted the doc's claimed
  account-level `is_launderer` flag doesn't exist in the raw data — laundering labels
  are transaction-level only.
- Added `concepts/14-spark-and-pyspark.md`: what Spark/PySpark are, why used here
  despite laptop-sized data, `local[*]` vs. a real cluster, the JAVA_HOME/JVM
  dependency, and the broadcast-join + left-semi-join filtering pattern used in the
  subsampling job.

**Decisions made:**
- Guaranteed-inclusion + random-topup sampling strategy for the AML subsample (see
  above), documented in both `data/README.md` and the job's own module docstring.
- `pyspark` isolated to an `analytics` uv dependency group rather than a core
  dependency, matching the module boundary in scoping doc Section 6.16.

**Current state:**
- **Phase 0 (Prep) is complete** — every gate item in `docs/ROADMAP.md` is checked.
- Local dev environment now includes a working Spark/PySpark setup usable for the
  next Spark job (telemetry aggregation, Phase 2/3).

**Next steps:**
1. Move into Phase 1 (Foundation): FastAPI gateway request lifecycle — Stage 1
   (ingress) + Stage 2 (parse) via the MCP Python SDK, naive forward with no policy or
   audit yet, tested against a real trivial upstream MCP server.
2. Introduce FastAPI as a concept when that work starts.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.

---

## 2026-07-20 — Project kickoff: scaffold, environment, first data, rename, GitHub setup

**What happened:**
- Read the full `docs/INTERPOSE_SCOPING.md` (287KB planning doc) and confirmed shared
  understanding of the project before writing anything.
- Scaffolded the repo per the scoping doc's Section 6.16 layout; established `CLAUDE.md` and
  `concepts/` as working conventions (one plain-language explainer per new tool/domain idea).
- Adapted the scoping doc's fixed day-by-day plan (Section 14) into `docs/ROADMAP.md` — same
  phases and gates, but paced by understanding rather than the calendar.
- Set up local dev environment: `uv`-managed Python 3.12, Docker, `kubectl`, `helm`,
  `terraform`, `kind` — each installed and verified working (not just installed — actually ran
  a `kind` cluster up/down, ran a real MCP client/server round trip).
- Caught and fixed a Homebrew `autoremove` side effect that had silently uninstalled `node` and
  `mongosh`; reinstalled both.
- Downloaded and validated the OFAC SDN sanctions list (19,169 entries) and the IBM AML
  HI-Medium dataset from Kaggle (31.9M transaction rows, ~2.8GB) — corrected two scoping-doc
  inaccuracies along the way (HI-Medium is ~32M rows, not ~180M as stated; the dataset's actual
  license is CDLA-Sharing-1.0, not CC-BY 4.0).
- Renamed the project from "Sentinel" (felt generic) to **Interpose**, throughout the repo,
  local data directories, and all documentation.
- Created the GitHub repo, pushed `main`, added standard OSS scaffolding (`CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, issue/PR templates, GitHub Actions CI),
  adopted **GitHub Flow** as the branching convention, and set branch protection on `main`
  (PR + passing CI required; verified live that admin bypass is possible by design).
- Added 13 `concepts/` docs so far (00 through 12): CLAUDE.md files, MCP, the
  Interpose/gateway architecture, SLA/SLO/latency, the AML/OFAC glossary, Python envs & `uv`,
  containers & Docker, Kubernetes, Terraform/IaC, the MCP handshake, open data licensing,
  git branching & GitHub Flow, and OSS community-health files.

**Decisions made:**
- Branching model: GitHub Flow (not GitFlow, not trunk-based-forever) — see
  `concepts/11-git-branching-and-github-flow.md`.
- Learning pace over calendar pace: ~30 days, flexible by about a week, gated on actually
  understanding each concept, not on hitting fixed days.

**Current state:**
- Phase 0 (Prep) nearly complete. Repo, environment, CI, and both source datasets are in place.
- Only remaining Phase 0 item: **subsample the IBM AML dataset down to ~500K accounts**, which
  requires setting up Spark/PySpark locally first (a new tool + concept, not yet introduced).

**Next steps:**
1. Set up Spark/PySpark locally (new concept doc needed: what Spark is, why a distributed
   processing engine for a laptop-sized job, Java runtime dependency).
2. Run the subsampling job per `docs/INTERPOSE_SCOPING.md` Section 10.3 (seed 42, ~500K
   accounts, verify laundering-label ratio and graph connectivity preserved).
3. That completes Phase 0's gate — move into Phase 1 (Foundation): the FastAPI gateway request
   lifecycle.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should be rotated (Settings → API →
  regenerate) — flagged, not yet confirmed done.
