# Session log

Purpose: a new session (new context window, possibly a new machine) should be able to read this
file and know *exactly* where things stand — not just which phase we're in (`docs/ROADMAP.md`
covers that), but what happened last time, what was decided, and what the immediate next step
is. See `concepts/13-session-continuity-and-progress-logs.md` for why this file exists and how
it fits alongside `CLAUDE.md`, `docs/ROADMAP.md`, and `CHANGELOG.md`.

Newest entry first. One entry per work session (not necessarily per calendar day).

---

## 2026-08-13 (cont'd) — Phase 4 scoped; Day 16, the real adversarial test suite, built and live-verified

**What happened:**
- Scoped Phase 4 (docs/ROADMAP.md's Proof & Polish): surveyed what actually blocks
  each of its four pieces before touching anything. Found the adversarial suite
  (`tests/adversarial/`) was cheaper than its own README claimed -- both gateway
  capabilities its two most-blocked attack classes needed (a response-side policy
  hook; real `pii_redaction`) were already built in Phase 3 Day 14, the README just
  never got updated. Also found: Section 11.7's Spark Operator work was already
  implicitly cut (absent from ROADMAP's own Day 16-20 list); an eval harness +
  "evaluation report JSON" is referenced in Section 4.6/14.8 but was never actually
  scheduled anywhere. Confirmed five real scope decisions with the user before
  starting: adversarial suite first; Terraform/EKS module-only this phase (no live
  apply); skip Spark-on-K8s (stays v0.2); build a lightweight eval harness reusing
  the adversarial suite; and (corrected mid-conversation, see below)
  `prompt_injection_via_tool_output` gets detect-and-tag only, not a block.
- Built the real adversarial suite for all 6 required attack classes (Day 16, gate
  G9): `tests/adversarial/harness.py` (a real gateway + real upstream subprocess
  pair per attack class, a real MCP client driving scripted calls, assertions
  against the real audit trail/response/incidents table -- never gateway
  internals), `generate.py` (real seeded scenario templates, replacing the
  `NotImplementedError` skeleton), and `test_live_scenarios.py` (all 6 classes, live,
  in CI).
- **Two real design mistakes, both caught by running things live, both fixed by
  restructuring rather than patching:** (1) Tried putting a new allowlist demo
  policy in the same directory as the existing hitl_gate/rate_limit demo policies --
  broke two pre-existing tests, because `PolicySet.evaluate`'s allowlist check is an
  unconditional early return that bypasses denylist/rate_limit/hitl_gate entirely
  for every tool on that server, not just the ones it lists. Reverted the shared-pack
  attempt entirely (including the two test edits) and gave each attack class its
  own fully isolated `policy_dir`
  (`tests/adversarial/fixtures/policies/<attack_class>/`), so one class's policies
  can never interact with another's regardless of contents. (2) Initially told the
  user a response-side custom policy could "fail-closed block" a tainted response --
  wrong; `interpose.policies.custom`'s own docstring says response-side policies
  can never deny an already-completed call, confirmed against `aml_structuring_alert`'s
  real precedent (tags only, never blocks). Went back to the user with the
  correction before writing more code; landed on detect-and-tag, matching that
  exact precedent, honestly documented as not blocking.
- Deliberately scoped fixture volume down from Section 10.5's literal ~500-1000
  variants/class (confirmed with the user first): 2-4 real, seeded variants per
  class instead, each varying a genuine axis where one exists (which PII pattern;
  how many repeated denials), not padded to a bigger number for its own sake.
- Added `interpose.policies.packs.demo` (the new `hello_echo_prompt_injection_scan`
  custom policy) and three new hello-echo demo tools (`echo_untrusted`, `leaky_echo`
  -- kept even after moving off the shared-pack design, since isolated
  policy-per-class removed the collision risk that motivated them in the first
  place, and the distinct names still read better in scenario descriptions than
  overloading `echo`).
- Wired CI: a new, separately-named `adversarial` job (`.github/workflows/ci.yml`)
  rather than letting `tests/adversarial/` run silently inside the general `test`
  job (`testpaths = ["tests"]` would have picked it up either way) -- "CI job runs
  the full adversarial suite... as a claim" is a specific thing this project
  claims, so it gets a specific, visibly-labeled check. `test` now excludes
  `tests/adversarial/` to avoid double-running the same 22 live scenarios.
- Closed the eval-harness gap without inventing a new concept: `tests/adversarial/harness.py`'s
  `run_scenario`/`assert_scenario_result` already *is* an evaluation harness
  (Section 12.2's own definition -- run a scripted scenario against the real
  system, check pass/fail) built for a different immediate purpose. `scripts/run_eval_report.py`
  reuses it directly, pointed at producing a JSON summary instead of raising a
  pytest failure; CI uploads it as a build artifact every run
  (`actions/upload-artifact`), the same file Day 20's release process attaches to
  v0.1.0 rather than a separately-generated one.
- Rewrote `tests/adversarial/README.md` to match reality; added
  `concepts/35-adversarial-testing-and-evaluation.md` covering both design
  mistakes, what each attack class actually proves, and the eval-harness reuse
  reasoning.
- Full local suite green twice back-to-back (327 passed both times, up from 305 --
  22 new live adversarial tests), `ruff`/`helm lint` clean.

**Decisions made:**
- One isolated `policy_dir` per attack class, not one shared adversarial pack --
  structural fix, not a one-off patch, for the allowlist-bypasses-everything-else
  behavior found live.
- `prompt_injection_via_tool_output` detects and tags, does not block -- matches
  `interpose.policies.custom`'s existing documented design boundary and
  `aml_structuring_alert`'s real precedent; building a genuine response-side block
  would have been new gateway scope, explicitly declined.
- 2-4 real fixture variants per class, not Section 10.5's literal ~500-1000 -- CI
  cost of the 500th near-identical variant isn't worth its marginal signal.
- Spark-on-Kubernetes (Section 11.7) stays out of scope for v0.1.0, confirmed
  explicitly rather than left ambiguous.
- Terraform/EKS work (next up) is module-only this phase -- build and validate, no
  live `terraform apply` against real AWS without a separate, explicit go-ahead.

**Current state:**
- Phase 4 Day 16 (adversarial test suite) is done, real, and live-verified for all
  6 required attack classes -- gate G9 met. The eval-harness gap referenced in
  Section 4.6/14.8 but never scheduled anywhere is also closed, same session.
- Not yet committed at the time of writing.

**Next steps:**
1. Terraform + EKS module (Day 17): build `terraform/aws-eks/` per Section 11.6 (VPC,
   EKS, RDS, ElastiCache, S3, IAM/IRSA, KMS, CloudWatch, `examples/minimal/`) --
   module-only this phase, no live AWS apply without explicit separate sign-off
   (real ~$150-200/month while running).
2. Then blog posts (Days 18-19) and the demo video, both meant to stay in the
   owner's own voice -- support material (diagrams, data, drafts to react to), not
   ghostwritten wholesale.
3. Day 20: release polish, v0.1.0 tag, Helm chart + image publishing.

**Loose ends / reminders:**
- Carried over, still open: Part 2 (control-plane persistence)'s in-cluster
  verification, `interpose demo aml --run`'s audit-verification DB mismatch against
  a remote gateway. Neither blocking.

---

## 2026-08-13 — Live-verifying the Prometheus pipeline, and a real histogram bucket bug

**What happened:**
- Docker was back up; did the in-cluster live verification PR #17 (2026-08-10/12
  entry) had explicitly deferred. Recycled the `kind` cluster fresh, confirmed
  `otelCollector.enabled`/`prometheus.enabled` bring up both pods automatically from
  `values-dev.yaml`'s defaults with no extra steps.
- Drove real MCP traffic through the gateway (`echo` calls, one deliberate policy
  denial) and verified the whole pipeline end to end, at every hop rather than just
  the final dashboard: `OTEL_EXPORTER_ENDPOINT` correctly set on the gateway pod;
  the Collector's own `/metrics` endpoint showing real `interpose_tool_calls_total`/
  `interpose_policy_fires_total` data; Prometheus's scrape target reporting
  `"health": "up"`; the real, chart-deployed Grafana's Prometheus datasource
  provisioned correctly; Dashboard 1's actual panel queries, run through Grafana's
  own `/api/ds/query` endpoint (not a temporary standalone Grafana this time -- the
  real one), returning a real non-zero rate curve exactly when traffic happened.
- **Found and fixed a real bug this live check caught, that nothing else would
  have:** the OTel SDK's default histogram bucket boundaries
  (`[0, 5, 10, 25, ... 10000]`) are tuned for millisecond-scale values; the
  `interpose_tool_call_duration_seconds` histogram records in *seconds*, so every
  real ~30ms tool-call latency landed in the same first bucket (`le=5`, meaning 5
  *seconds*), and `histogram_quantile()` linearly interpolated across that one wide
  bucket as if latencies were uniformly spread across 0-5s -- reporting a p95 of
  4.75 seconds for calls that actually took ~25ms. All unit tests passed, `ruff` was
  clean, the Collector's raw `/metrics` output even looked plausible at a glance --
  only computing a real `histogram_quantile()` against real Prometheus data
  surfaced it. Fixed with `create_histogram(...,
  explicit_bucket_boundaries_advisory=[...])` (an OTel Python SDK API for exactly
  this), boundaries set to the OTel/Prometheus semantic-convention default for a
  seconds-denominated duration histogram (the same millisecond set, divided by
  1000, capped at 10s -- HITL holds can take up to an hour, but that's what
  `interpose_gateway_inflight` is for, not this histogram). Rebuilt the image,
  redeployed in-cluster, re-verified with fresh traffic: p50/p95 came back as
  0.0175s/0.02425s -- correct, sane numbers. Documented in
  `concepts/34-metrics-and-prometheus.md` and guarded with a new unit test
  (`test_duration_bucket_boundaries_are_sub_second_resolution`).
- Full local suite green with Docker actually up this time (314 passed, including
  integration tests that couldn't run in the prior two sessions), `ruff` clean.
  Cluster and `docker-compose` stack torn down cleanly at the end.

**Decisions made:**
- None new -- this session was verification of already-merged work, plus the one
  bug fix it surfaced.

**Current state:**
- Phase 3's Prometheus/metrics gap (part 3) is now genuinely live-verified
  in-cluster, not just unit-tested and helm-templated as PR #17 originally shipped
  it. The histogram bucket-boundary fix is real, correctness-affecting, and needs
  its own PR before Dashboard 1's latency panels can be trusted.
- Not yet committed at the time of writing.

**Next steps:**
1. Commit and PR this session's fix (histogram bucket boundaries + the new test +
   concept doc update), same branch-per-gap workflow as the prior three.
2. All three of Phase 3's named gaps are now closed *and* live-verified except Part
   2 (control-plane persistence)'s in-cluster check, still explicitly deferred per
   the 2026-08-05/06 entry -- optional, low-priority, revisit if it becomes
   load-bearing (e.g. before recording the demo video).
3. Then: Phase 4 (adversarial test suite, Terraform/EKS, blog posts, demo video,
   v0.1.0 tag).

**Loose ends / reminders:**
- Part 2 (control-plane persistence)'s in-cluster verification is still the one
  deliberately-skipped check across all three gap-closing sessions -- not urgent,
  but worth remembering it's the one gap that was never actually run against a real
  cluster.
- `interpose demo aml --run`'s audit-verification DB mismatch against a remote
  gateway -- still open, still not urgent.

---

## 2026-08-10/12 — Closing Phase 3's named gaps, part 3 (final): real Prometheus metrics, Dashboard 1 rewired — Phase 3's named gaps fully closed

**What happened:**
- Closed the third and last of Day 15's named gaps: no Prometheus/`/metrics`,
  Dashboard 1 (Gateway Health) left as a Postgres/audit-log approximation.
- Added `src/interpose/observability/metrics.py`: five OTel instruments matching
  Section 12.3's golden-signal table exactly (`interpose_tool_calls_total`,
  `interpose_tool_call_errors_total`, `interpose_tool_call_duration_seconds`,
  `interpose_gateway_inflight`, `interpose_policy_fires_total`). Reuses the same
  OTLP pipeline the existing tracing setup already uses
  (`Settings.otel_exporter_endpoint`) rather than a separate `prometheus_client` +
  hand-rolled `/metrics` endpoint -- one dependency set, no new packages needed
  (`opentelemetry-sdk`/`opentelemetry-exporter-otlp-proto-grpc` already cover metrics
  as well as traces). `interpose_gateway_inflight` is an `UpDownCounter`, not an
  OTel "gauge" -- a gauge is callback-based (report the current value on request),
  which doesn't fit "increment on call start, decrement on call end" at all; the
  Collector's Prometheus exporter renders an UpDownCounter as a Prometheus gauge on
  export regardless, so the end result looks the same to Grafana either way.
- Wired all five into `src/interpose/gateway/app.py` at the points that already
  compute each value -- no new tracking state. Saturation + duration wrap
  `_handle_tool_call`'s one call site in `proxy_mcp` (covering policy evaluation,
  any HITL wait, and the upstream forward as one "in flight" span, not just the
  final forward call); tool-calls/errors are recorded at each existing
  terminal-outcome branch; policy fires reuse the exact `policies_fired` list
  already written to `audit_entries.policies_fired`, so "fired" means the same
  thing in both places.
- Added an OTel Collector and a single-replica Prometheus to the Helm chart
  (`charts/interpose/templates/otel-collector/`, `.../prometheus/`) -- no Prometheus
  Operator/PodMonitor CRD, since nothing in this project installs one; a plain
  static scrape config pointed at the Collector's exporter port is the honest
  minimal-machinery equivalent. Both gated behind `otelCollector.enabled` /
  `prometheus.enabled`, defaulting `false` in `values.yaml` (production-leaning:
  Section 11.8 says real deployments bring their own backend) and `true` in
  `values-dev.yaml` (self-contained kind install) -- same embedded-vs-external split
  `postgres.embedded`/`redis.embedded` already established.
- Added a second Grafana datasource (Prometheus) and fully rewrote Dashboard 1
  around real PromQL panels (tool calls/sec by outcome, latency percentiles via
  `histogram_quantile`, error rate, saturation, per-server health table) -- replacing
  the fixed-window Postgres approximation entirely rather than keeping both, since
  Dashboard 1's synthetic panels were always explicitly named as temporary
  scaffolding (unlike Dashboards 2/3's synthetic panels, which represent a
  genuinely large demo corpus still worth keeping). Named, honestly, what's still
  not shown: circuit breaker states (no circuit breaker exists in the gateway) and
  AlertManager/alert rules (Prometheus itself is real now; nothing pages anyone
  yet).
- Added `concepts/34-metrics-and-prometheus.md` and a `tests/unit/observability/`
  suite (6 tests: every `record_*`/`inflight_*` function is safe to call without
  `setup_metrics` ever running -- the same no-op-meter fallback the app relies on
  whenever `OTEL_EXPORTER_ENDPOINT` is unset -- plus one test confirming instruments
  are created once and reused, not rebuilt per call).
- **Live verification of this gap was not done this session** -- Docker wasn't
  running (see "Loose ends"). What's verified instead: `helm lint`/`helm template`
  clean for both the dev overlay (`otelCollector.enabled=true`) and bare
  `values.yaml` (both off, confirming production mode stays minimal -- 4
  Deployments, no `OTEL_EXPORTER_ENDPOINT` set at all), full local unit suite green
  (259 passed), `ruff` clean. CI (which has its own Postgres/Redis) is the first
  real integration-test run this change gets; merged only after those checks pass.

**Decisions made:**
- Reused the existing tracing OTLP pipeline for metrics rather than a parallel
  `prometheus_client` integration -- deliberate, not just convenient: one pipeline,
  one endpoint setting, one Collector receiving both signals.
- Dashboard 1's synthetic panels were fully replaced, not kept alongside the new
  real ones (unlike Dashboards 2/3's approach in the prior two sessions) -- they
  were always named as a stand-in for what this session builds, not a demo artifact
  worth preserving on its own.
- `otelCollector`/`prometheus` default off in production values, on in dev values --
  consistent with the existing Postgres/Redis embedded-vs-external pattern and
  Section 11.8's stated "bring your own backend" philosophy for real deployments.

**Current state:**
- **All three of Phase 3's named gaps are now closed**: both AML MCP servers real
  and policy-enforced in-cluster (part 1), control-plane anomaly/incident/risk-score
  history persisted and dashboarded (part 2), real Prometheus metrics with Dashboard
  1 rewired around them (part 3, this entry).
- Not yet committed at the time of writing -- working tree has the full gap-3-part-3
  diff staged for a commit this session, `docs/INTERPOSE_SCOPING.md`'s stray
  whitespace diff (same one carried since before this three-part effort started)
  left out again.
- Docker was not running this session -- no `kind` cluster exists right now; the
  in-cluster state from the part-1/part-2 sessions is long gone (recycled once,
  never recreated after). Next session touching the cluster starts cold either way.

**Next steps:**
1. Reassess Phase 4 (adversarial test suite, currently a Day-10 skeleton; Terraform
   module + real EKS deploy; two blog posts; edited demo video; the v0.1.0 tag) now
   that every Phase 3 named gap is closed.
2. Optional, low-priority, carried over from part 2: in-cluster live verification of
   both the control-plane persistence tables and this session's Prometheus pipeline,
   if it becomes load-bearing later (e.g. before recording the demo video) --
   neither is blocking today.

**Loose ends / reminders:**
- Docker wasn't running this session; nothing here was live-verified against a real
  `kind` cluster or a real scraped Prometheus target -- CI's own test run is the
  first real integration check this change gets.
- Carried over, still open: `interpose demo aml --run`'s audit-verification DB
  mismatch against a remote gateway; in-cluster verification for Part 2's
  persistence tables.

---

## 2026-08-05/06 — Closing Phase 3's named gaps, part 2: control-plane decisions now persisted

**What happened:**
- Closed the second of the three named gaps from Day 15 (see the prior entry): Agent
  A2's anomaly flags, Agent A4's incident promotions, and Agent A1's session risk
  score were all computed for real but discarded the moment a graph run finished
  (A1's risk score fared slightly better -- written to an ephemeral Redis hash that
  gets overwritten on every decision, so still no history).
- Added `src/interpose/control_plane/models.py`: three new tables
  (`anomaly_flags`, `incidents`, `risk_score_snapshots`) sharing
  `interpose.audit.models.Base`, same one-migration-history reasoning as
  `interpose.analytics.models`. Deliberately no foreign key back to
  `audit_entries.id` -- matches `AuditEntrySynthetic.parent_id`'s existing precedent,
  and several of this project's own control-plane tests use a fixed placeholder
  `audit_id` that was never seeded, which a hard FK would break for no real benefit.
- Wired persistence into the three existing node closures
  (`anomaly_detector.py`, `incident_escalator.py`, `policy_evaluator.py`) right where
  each value already exists, using the `session_factory` already bound into each
  closure for their own feature/signal queries. Generated and applied the Alembic
  migration (`2a594d020568`); registered `control_plane.models` in `alembic/env.py`
  alongside `analytics.models`.
- Deliberately did **not** add a Spark aggregation step for this data, unlike Day 15's
  `agg_*` tables: those exist because the 10M-row synthetic corpus is too large to
  query directly at interactive speed, but real control-plane traffic runs at tens to
  low thousands of rows in this project's own use -- a plain `GROUP BY`/`WHERE
  created_at > ...` query straight from the Grafana panel is simpler and just as
  fast. Documented this reasoning in the new
  `concepts/33-persisting-control-plane-decisions.md`.
- Replaced Dashboard 2's "Anomaly clusters / incident promotions" and Dashboard 3's
  "Session-level risk score distribution" named-gap text panels with real SQL panels
  (severity breakdown + a recent-incidents table; a risk-score histogram), each using
  a `timeFrom: "30d"` override since this data doesn't share the other panels' fixed
  synthetic-data window.
- Strengthened `tests/integration/test_control_plane_graph.py`'s existing acceptance
  tests to assert the new DB rows match the in-memory `InterposeState` exactly
  (severity, evidence, narrative, promotion rule), not just that the graph produced
  *something*.
- **Two real bugs, both caught by running the suite more than once, not by a single
  green run:** (1) `tests/integration/conftest.py`'s `clean_state` fixture only
  truncated `audit_entries`, not the three new tables -- invisible until the full
  suite ran twice in a row, at which point a leftover row from the first run broke a
  "read exactly one row for this session_id" assertion in the second. Fixed by
  truncating all three tables in the same fixture. (2) Several of this test file's
  own scenarios call both `_node_sequence` (a real `astream` run) and `ainvoke` (a
  second real run) against the *same* input state to check both routing and output --
  meaning two matching rows land in the new tables per test, not one. Fixed by
  ordering the read-back query and taking the most recent row, with a comment
  explaining why more than one row is expected there.
- **Live-verified locally, thoroughly:** ran a real temporary Grafana container
  (same provisioning config the Helm chart uses) against real Postgres data, queried
  the three new panels directly via Grafana's own `/api/ds/query` endpoint --
  confirmed correctly-shaped rows, not just "the JSON parses." Ran the full local
  test suite twice back-to-back post-fix (307 passed both times) to prove the
  isolation fix actually holds, not just that it passed once. `ruff` clean.
- **In-cluster verification was attempted but not completed, and deliberately left
  that way** -- see "Loose ends" below. The code itself is solid (thorough local
  verification above); what's unverified is specifically the in-cluster path.

**Decisions made:**
- No Spark pre-aggregation for control-plane persistence tables -- direct query
  against the raw tables is correct at this data's real scale; matches the
  reasoning `concepts/33-persisting-control-plane-decisions.md` documents.
- No FK from the three new tables back to `audit_entries` -- consistency with
  `AuditEntrySynthetic`'s existing precedent, and avoids forcing every existing
  control-plane test to seed a real audit row it doesn't otherwise need.
- Stopped chasing in-cluster verification once it became clear most of the "hangs"
  were self-inflicted testing mistakes (stale port-forwards, retrying against MCP
  servers still mid-startup, not running a concurrent HITL approver) rather than
  bugs in the persistence code -- user's explicit call to leave it as-is rather than
  keep spending session time proving something the local suite already proves.

**Current state:**
- Two named gaps closed, live-verified in the ways described above. One remains:
  Prometheus/metrics (Dashboard 1 still a Postgres approximation).
- Not yet committed -- working tree has the full gap-3 diff staged for a commit this
  session, same `docs/INTERPOSE_SCOPING.md` stray whitespace diff as before left out.
- Docker was not running at the end of this session; the `kind` cluster state from
  the debugging session is gone (recycled once already mid-session, not recreated
  after). Next session doing in-cluster work starts from a cold cluster either way.

**Next steps:**
1. Prometheus/metrics (the third and last named gap): OTel Meter-based
   counters/histograms for the 5 named metrics (scoping Section 12.3) in the
   gateway, a new OTel Collector in the chart (OTLP receiver + Prometheus exporter),
   Prometheus itself (or a `PodMonitor`) in-cluster, a second Grafana datasource,
   Dashboard 1 rewired off its Postgres approximation.
2. Then reassess Phase 4 (adversarial test suite, Terraform/EKS, blog posts, demo
   video, v0.1.0) with all of Phase 3's named gaps closed.
3. Optional, low-priority: revisit in-cluster verification of gap 3's persistence
   (real anomaly/incident/risk-score rows landing in the cluster's own Postgres via
   a full HITL-approved AML flow) if it becomes load-bearing later -- not blocking,
   since local verification is thorough and the code path through the gateway is
   identical either way.

**Loose ends / reminders:**
- In-cluster verification for gap 3 is genuinely incomplete, by explicit user
  decision, not an oversight -- don't assume it's been checked in-cluster if this
  comes up later.
- `interpose demo aml --run`'s audit-verification DB mismatch against a remote
  gateway (flagged in the prior entry) -- still open, still not urgent.

---

## 2026-08-04 (cont'd) — Closing Phase 3's named gaps, part 1: both AML MCP servers real and enforced in-cluster

**What happened:**
- Scoped all three named gaps left open by Day 15 (no Prometheus/`/metrics`, AML MCP
  servers not deployed in-cluster, control-plane anomaly/incident/risk-score not
  persisted) and agreed an order: AML in-cluster first (smallest, unblocks realistic
  Phase 4 adversarial testing), then control-plane persistence, then Prometheus --
  with Prometheus done now against `kind` rather than deferred to Phase 4's EKS work,
  since the OTel Collector + PodMonitor shape is the same either way.
- Deployed `ofac-sanctions` in-cluster (`dev/mcp-servers/ofac-sanctions.yaml`, direct
  copy of the `hello-echo.yaml` Deployment+Service pattern -- no host data dependency,
  it fetches live Treasury SDN/alt lists on pod start). Wired into
  `values-dev.yaml`'s `upstreams.servers`, `scripts/dev-up.sh`'s build/load/wait
  steps, `dev/mcp-servers/README.md`.
- Deployed `transaction-graph` in-cluster (`dev/mcp-servers/transaction-graph.yaml`),
  the real blocker: its ~150MB subsampled IBM AML Parquet dataset lives on the host,
  bind-mounted at `docker run` time locally, and a `kind` pod can't see the host
  filesystem without help. Added `kind.yaml` `extraMounts` on both worker nodes
  (not the control-plane node, which carries kind's default NoSchedule taint), driven
  by `$IBM_AML_DATA_DIR` (default `~/.interpose/data/ibm-aml`) -- rendered into the
  actual cluster config with `envsubst` before `kind create cluster --config -`,
  since a real absolute host path can't be safely hardcoded into a file committed to
  git. `dev-up.sh` now validates the directory exists before creating the cluster.
- **Real bug, not a fluke, caught by watching the pod actually crash-loop:**
  Kubernetes injects Docker-links-style env vars for every Service in a namespace
  into every pod (`<SVCNAME>_PORT=tcp://<clusterIP>:<port>`, etc.). The
  `transaction-graph` Service's own name happens to map exactly to that app's
  `TRANSACTION_GRAPH_` pydantic-settings env prefix, so Kubernetes silently
  overwrote `TRANSACTION_GRAPH_PORT` (meant to be an int) with a URL, and the
  container crashed on every start with a `pydantic_core.ValidationError`. Fixed
  with `enableServiceLinks: false` on all three dev fixture Deployments (added
  defensively to `hello-echo.yaml`/`ofac-sanctions.yaml` too, not just the one that
  actually hit it -- more services are joining this namespace in Gap 3/4's work).
- **Second real gap, found while trying to prove the AML pack was enforced
  in-cluster, not one of the three originally scoped:** the chart's policy
  ConfigMap (`configmap-policies.yaml`) only ever globbed
  `charts/interpose/files/policies/*.yaml` -- the Day 9/10 hello-echo demo pack.
  `policies/packs/aml/` was never wired into the chart at all, so a kind-deployed
  gateway could route to the real AML servers but had no AML policy enforcing
  anything on them. Asked the user; chose to close it now rather than defer.
  Fixed with a `policies.pack` values.yaml toggle (`hello-echo` default, `aml`
  opt-in via `--set` or `scripts/dev-up.sh`'s new `POLICY_PACK` env var), backed by
  a checked-in copy of the real pack at `charts/interpose/files/policies-aml/`
  (renamed the old directory to `files/policies-hello-echo/` to match) -- Helm's
  `.Files.Glob` can't read outside the chart directory, so this can't be a symlink
  or a live reference. Added `tests/unit/policies/test_chart_policy_sync.py` to
  catch drift between both chart copies and their real sources
  (`config/policies/`, `policies/packs/aml/`) -- nothing was catching this before.
- **Third real bug, found live-verifying the second fix:** setting
  `policies.pack=aml` and running `helm upgrade --wait` reported success, but the
  running gateway pod kept serving the *old* ConfigMap indefinitely -- Kubernetes
  never restarts a pod just because a ConfigMap it mounts changed, and this
  Deployment had no mechanism forcing one. Fixed with `checksum/config`,
  `checksum/policies`, `checksum/upstreams` annotations on the pod template
  (hashing each ConfigMap's rendered content) -- a real, general correctness fix
  that also covers `config/upstreams.yaml` changes, not just this demo's.
- Updated `interpose demo aml --setup`'s CLI text (`src/interpose/cli/demo.py`) to
  match reality and pass `POLICY_PACK=aml` through to `dev-up.sh` automatically.
  Updated `mcp-servers/transaction-graph/README.md`,
  `concepts/26-helm-and-the-interpose-chart.md`, and
  `charts/interpose/README.md` (install snippet, chart contents, "not deployed by
  this chart" section) to stop describing the old single-server, single-pack state.
- **Live-verified extensively, not just unit-tested:** a real `kind` cluster with
  all three MCP servers running; a real MCP client round-trip through the gateway
  to `ofac-sanctions` (matched a real SDN entry, IRGC, 100% score) and to
  `transaction-graph` (`get_account` on a real subsampled account, confirmed the
  hostPath mount actually exposes host data inside the pod); a real
  `aml-sanctions-required` denial when calling `transaction-graph` before an OFAC
  check, then a real `aml-write-hitl-gate` hold on `mark_investigated`, approved by
  a concurrent task simulating a reviewer, completing successfully; and a full
  `interpose demo aml --run` against the in-cluster gateway with a real Groq call,
  producing a genuine high-risk sanctions-match investigation with a real narrative
  and a real HITL-approved escalation write. Queried the cluster's own Postgres
  directly afterward: 27 real audit entries, correct tags (`pack:aml`,
  `regulation:BSA`, `sanctions-precondition`, `hitl`, `pii-redaction`), correct
  HOLD/PASS outcomes. Full local test suite still green throughout (307 passed, up
  from 305 -- the two new sync-check tests), `ruff` clean.

**Decisions made:**
- Prometheus/metrics (the third named gap) will be done now against `kind`, not
  deferred to Phase 4's EKS work -- user's explicit choice, since standing up an
  OTel Collector + Prometheus is the same shape either way and doing it once now
  means Dashboard 1 is real before Phase 4 starts.
- The newly-found AML-pack-not-wired-into-the-chart gap was closed immediately
  rather than left as a fourth deferred item -- user's explicit choice, reasoning
  being it directly blocks a genuine in-cluster AML demo, the actual point of
  closing the other two gaps.
- `policies.pack` defaults to `hello-echo`, not `aml` -- keeps the Day 9/10 baseline
  behavior of a bare `dev-up.sh` run unchanged; the AML pack is opt-in via
  `POLICY_PACK=aml` (which `interpose demo aml --setup` now sets automatically).

**Current state:**
- Two of Phase 3's three named gaps are closed and live-verified: both AML MCP
  servers are real, working, policy-enforced in-cluster deployments, not local
  subprocesses-only. A fourth, previously-unflagged gap (AML pack not wired into
  the chart) was found and closed in the same session.
- The `kind` cluster (`interpose-dev`) is currently up, with `policies.pack=aml`
  installed (via a manual `helm upgrade --set policies.pack=aml`, not yet re-run
  through a fresh `dev-up.sh` with `POLICY_PACK=aml` -- functionally identical, just
  noting the exact path taken). Left running rather than torn down, to avoid
  re-paying the ~2-3 minute rebuild cost before tomorrow's session. Two
  `kubectl port-forward`s are active in the background: gateway on `:8000`, kind's
  own Redis on `:6380` (not `:6379` -- that port is `docker-compose`'s Redis,
  needed simultaneously for the local pytest suite against the bare/local stack).
- One known, minor, deliberately-not-fixed limitation: `interpose demo aml --run`'s
  final audit-chain-verification step reads `DATABASE_URL` from local
  `Settings` (the `docker-compose` Postgres), so it reports "No audit entries
  found" when `--gateway-url` points at the kind cluster's own gateway/Postgres
  instead of a co-located bare gateway. The investigation and audit trail
  themselves are genuinely correct in that case (verified directly via `psql`
  against the cluster's Postgres above) -- only the CLI's own verification step is
  looking at the wrong database. A `--database-url` option would fix it; flagged,
  not built, since it's outside today's three scoped gaps.

**Next steps:**
1. Control-plane anomaly/incident/risk-score persistence (the second gap in the
   agreed order): new tables (`anomaly_flags`, `incidents`, a risk-score history
   table) sharing `audit.models.Base`, written synchronously inside
   `anomaly_detector.py`, `incident_escalator.py`, and `policy_evaluator.py`'s node
   closures where results are currently discarded; an Alembic migration; swap
   Dashboard 2/3's two literal "named gap" text panels for real SQL panels.
2. Prometheus/metrics (the third, agreed to happen now, not deferred to Phase 4):
   OTel Meter-based counters/histograms for the 5 named metrics (scoping Section
   12.3) in the gateway, a new OTel Collector in the chart (OTLP receiver +
   Prometheus exporter), Prometheus itself (or a `PodMonitor`) in-cluster, a second
   Grafana datasource, Dashboard 1 rewired off its Postgres approximation.
3. Then reassess Phase 4 (adversarial test suite, Terraform/EKS, blog posts, demo
   video, v0.1.0) with all of Phase 3's named gaps actually closed.

**Loose ends / reminders:**
- `interpose demo aml --run`'s audit-verification DB mismatch against a remote
  gateway (see "Current state" above) -- not urgent, but worth a `--database-url`
  option eventually.
- The `kind` cluster is currently up with manual port-forwards running (`:8000`
  gateway, `:6380` kind-Redis) rather than through `dev-up.sh`'s own managed
  port-forward + PID-file mechanism -- tomorrow's session should either reuse these
  or restart cleanly via `scripts/dev-down.sh && scripts/dev-up.sh`.

---

## 2026-08-04 — Phase 3 Day 15: Spark analytics, Postgres-backed dashboards — Phase 3 complete

**What happened:**
- Started by investigating what Day 15 actually needed before touching anything: all
  four Grafana dashboards (provisioned Day 9) were wired to a Prometheus datasource
  that was never actually configured, pointing at a Prometheus that was never
  deployed, with nothing exporting `/metrics` either -- they'd have shown a
  connection error, not empty panels. Section 10.6, separately, describes exactly
  what Day 15's own roadmap bullets ask for: a Postgres-centric pipeline (Spark
  generates synthetic telemetry into Postgres, a second Spark job aggregates it into
  Postgres summary tables). Asked the user how to resolve this; chose to rebuild all
  four dashboards on Postgres, including approximating Dashboard 1 (Gateway Health)
  from the audit log's own columns rather than leaving it Prometheus-shaped.
- Built `interpose.analytics.generate_synthetic_telemetry`: 10,004,966 synthetic
  tool-call rows, 500 agents, 100 tools across 20 servers (2 real --
  `ofac-sanctions`/`transaction-graph`, for Dashboard 3 continuity -- 18 generic), a
  fixed 4-week window with a real diurnal cycle + weekend dip, 3 incident windows, 1
  coordinated-attack simulation. Generated in under a minute -- the per-hour target
  row count is computed once on a 672-row bucket table, then exploded directly into
  that many rows, avoiding a join against the full 10M rows that a naive
  weighted-sampling implementation would have needed.
- New `audit_entries_synthetic` table (schema mirror of `audit_entries`, unchained
  placeholder hashes -- tamper-evidence is a real-audit-log property, not something
  fabricated demo data needs) plus 5 new aggregate tables
  (`interpose.analytics.models`), all sharing `audit.models.Base`'s metadata so one
  Alembic migration history covers both planes.
- **Tried Spark's JDBC write first, it didn't work.** `spark.jars.packages` should
  fetch the Postgres driver from Maven via Ivy at runtime; Ivy resolution came back
  empty with no error, despite confirming this environment has real internet access.
  Not worth chasing down for a one-time demo loader, and this project has no other
  Spark-to-Postgres precedent anyway (the audit store itself writes via SQLAlchemy).
  Pivoted to the simpler, already-proven pattern: Spark writes Parquet (like
  `subsample_aml.py` already does), a plain Python step (`pyarrow` + `COPY`,
  `interpose.analytics.load_synthetic_telemetry`) loads it into Postgres in
  batches. ~3.5 minutes for 10M rows.
- Built `interpose.analytics.aggregate_telemetry`: reads the synthetic Parquet
  directly (same JDBC-avoidance reasoning), produces all 5 aggregate tables in ~5
  minutes. Deliberately scoped to synthetic data only, not parameterized to also
  aggregate real `audit_entries` -- Section 10.6's own reasoning for generating
  synthetic telemetry in the first place is exactly why a Spark-*scale* job's value
  is demonstrated against the synthetic corpus, not the small real one.
- **Two real aggregation bugs, caught by checking row counts and category totals,
  not assumed correct because the query ran:** `agg_cost_daily` grouped by
  `{day, agent_id, tool, provider}` produced 918,819 rows (500 agents × ~100 tools ×
  2 providers × 28 days, most combinations appearing a handful of times) -- fixed
  by dropping `tool` from the grouping, matching what Section 12.4's panels
  actually ask for ("per agent," "per provider," never both at once).
  `agg_aml_pack_daily`'s `mark_investigated_pending` column double-counted with
  `_approved` (it summed every `COMPLETED` row, which includes the HITL-approved
  ones) -- renamed to `mark_investigated_auto_passed`, fixed to require
  `hitl_decision IS NULL`, and documented that this bucket is a synthetic-generator
  artifact: the real pack's `aml-write-hitl-gate` (Day 14) makes it impossible for
  real traffic.
- Rebuilt all four dashboard JSONs against the new Postgres datasource (added to the
  Helm chart's Grafana provisioning), each panel a real SQL query against the
  aggregate tables. Two panels (control-plane anomaly/incident data on Dashboard 2,
  session risk-score distribution on Dashboard 3) became explicit named-gap text
  panels instead of faked numbers -- that data is computed live by the control
  plane and never persisted anywhere historical.
- Wired `interpose demo aml --setup`/`--run` into the Typer CLI (Section 9.10) --
  shells out to the existing `scripts/dev-up.sh` and
  `agents/aml-investigator/run_investigation.py` rather than reimplementing either,
  then runs the same chain-verification `verify-audit` already does. `--setup`
  prints an explicit note that it doesn't deploy the AML MCP servers in-cluster
  (the same named gap Days 12-13 already flagged).
- 12 new tests (10 for the CLI command, subprocess/audit-query mocked; 2 for the
  loader's one pure-Python helper). The Spark jobs themselves have no unit tests,
  matching `subsample_aml.py`'s own established precedent -- verified live instead.
  305 total tests green, `ruff`/`helm lint`/`helm template` all clean.
- **Live-verified beyond the automated suite, twice:** a temporary real Grafana
  container (provisioned with the actual chart's datasource/dashboard config, not a
  mock) confirmed the Postgres datasource connects and every panel's SQL returns
  real, correctly-shaped data -- queried directly via Grafana's own `/api/ds/query`
  endpoint, not just checked for a 200 response. `interpose demo aml --run` executed
  for real against the AML-pack-loaded gateway with a real Groq call and a real HITL
  approve cycle (a concurrent task polling and approving, same pattern as every
  other day's HITL test), producing a 14-row chain-verified audit trail and the
  correct CLI output sequence end to end.

**Decisions made:**
- All four dashboards rebuilt on Postgres, not Prometheus -- user's explicit choice
  when asked, given no Prometheus exists anywhere in this project.
- Aggregation job scoped to synthetic telemetry only, not parameterized to real
  `audit_entries` too -- a deliberate, documented simplification, not an oversight.
- Spark writes Parquet + a plain Python COPY loads Postgres, not Spark JDBC --
  JDBC didn't work in this environment and there's no existing precedent for it.

**Current state:**
- Phase 3 Day 15 done and checked off. **Phase 3's gate is met and the phase is
  complete**: the AML demo runs end-to-end through a real HITL cycle with a
  chain-verified audit trail, and the Spark pipeline processes 10M synthetic
  records into working dashboards.

**Next steps:**
1. Phase 4 (Proof & Polish, `docs/ROADMAP.md`): the adversarial test suite (6+
   attack classes, currently a skeleton from Phase 2 Day 10), the Terraform module
   + real EKS deploy, two blog posts, an edited demo video, the v0.1.0 tag/release.
2. The video recording draft (Day 15's last bullet, Section 14.7) is a human
   screen-capture deliverable -- not something to build, left for the user
   whenever they're ready to record `interpose demo aml --run`.
3. Named gaps still open from earlier days, unresolved: no Prometheus/`/metrics`
   (Dashboard 1 remains an approximation); AML MCP servers not deployed in-cluster
   (Days 12-13); control-plane anomaly/incident/risk-score data not persisted
   anywhere historical (Dashboards 2/3's named-gap panels today).

**Loose ends / reminders:**
- None new this session.

---

## 2026-08-03 — Phase 3 Day 14: AML policy pack, and two protocol assumptions that were wrong

**What happened:**
- Built the AML policy pack (`policies/packs/aml/`), Phase 3 Day 14 per
  `docs/ROADMAP.md` -- 6 of Section 9.8's 7 policies active. Before writing any
  YAML, investigated what the pack would actually need from the engine (per CLAUDE.md's
  "explain before doing" habit) and found two real gaps: response-side (Stage 8)
  policy evaluation didn't exist at all -- the gateway only ever streamed raw,
  unparsed response bytes through -- and there was no "custom" policy mechanism for
  the two policies (`aml-sanctions-required`, `aml-structuring-alert`) that need real
  Python logic, not declarative YAML matching.
- Built both for real. `interpose.policies.custom`: a named-registry plugin design
  for custom policies (a security boundary -- policy YAML references code by name,
  never embeds it, since a pack is data a deployer drops in at runtime).
  `_forward_buffered`/`PolicySet.evaluate_response` in the gateway: only buffers and
  parses a response when the compiled `PolicySet` actually has a response-side
  policy, so every other call (the overwhelming majority) keeps the exact streaming
  path that's worked since Day 1 -- confirmed by the full existing suite (276 tests)
  passing unchanged before any AML-specific work even started.
- Real `pii_redaction` enforcement (regex-based: SSN, credit card, bank
  routing+account), replacing the Day-3 stub. New `tags` column on `audit_entries`
  (a real Alembic migration, included in the hash chain like every other field) backs
  `aml-audit-tagging`'s pack-wide labeling. `CostCapEffect` (P7) added as a
  schema-only stub, same status `pii_redaction` had for 10 days -- the gateway has
  no visibility into LLM token cost at all, so there's nothing real to enforce; the
  user chose this over a redefined "cost per tool call" version when asked directly.
- **Three real design flaws found before or via live testing, all fixed:**
  1. `aml-sanctions-required`'s first version correlated on `session_id`. Live-tested
     by opening two real connections through the same gateway to two different
     upstream servers and comparing session IDs directly: completely different
     values. `Mcp-Session-Id` is assigned independently by *each* upstream server
     during its own `initialize` handshake -- it was never going to correlate
     anything across servers. Redesigned around `agent_id` (the `Authorization`
     header) instead; `agents/aml-investigator`'s `InvestigationClient` now sends one
     consistent bearer token across both its connections so this actually works.
  2. The buffered response path assumed bare JSON; the very first live call failed
     with a JSON decode error. FastMCP's streamable-HTTP transport responds
     SSE-framed (`text/event-stream`) for every `tools/call`, never plain JSON --
     fixed with explicit SSE encode/decode helpers
     (`_decode_mcp_body`/`_encode_mcp_body`).
  3. `aml-sanctions-required`'s original `tools: ["*"]` scope would have gated
     `get_account` -- but `get_account` is the only source of the entity name
     `check_entity` needs, an unsatisfiable chicken-and-egg precondition. Fixed by
     excluding `get_account` from the policy's scope, and reordering the
     investigation agent's Discovery node to call `check_entity` immediately after
     `get_account`, before any other transaction-graph call.
  4. Smaller, found via the integration test itself: `InvestigationClient`'s error
     handling only ever checked `result.isError` (a tool-implementation error) --
     a gateway policy DENY is a JSON-RPC-envelope-level error, which the MCP SDK
     raises as `McpError` from `call_tool` itself rather than returning. This bug
     shipped on Day 13 and was invisible until today, since no policy pack existed
     yet to ever produce a real DENY.
- 37 new tests (unit: schema/dispatch/redaction/loader-manifest coverage; 6 new live
  integration tests driving the real pack through the real gateway + real MCP
  servers). 293 total tests green, `ruff` clean.
- **Live-verified twice more, beyond the automated suite**: once confirming the
  `agent_id` fix directly (two real connections, compared session IDs), and once
  running the full investigation agent end-to-end -- real Groq calls, a real HITL
  approve cycle (a concurrent task polling and approving the ticket, same pattern as
  Day 6's own HITL test), against the AML-pack-loaded gateway. Produced a clean
  14-row audit trail: sanctions-required correctly denying an out-of-order call,
  structuring-alert tagging a high-severity incident, the write HITL gate holding
  and then completing `mark_investigated`, every row tagged `pack:aml`/
  `regulation:BSA`.

**Decisions made:**
- P7 (`aml-cost-cap`): schema-only stub, not an active pack policy -- user's explicit
  choice when asked, given the gateway has no LLM-cost visibility at all.
- `aml-sanctions-required` and P4's rate limit are both intentionally narrower than
  Section 9.8's literal wording (agent-level not per-account; one threshold not two)
  -- documented in `policies/packs/aml/README.md`, not silently reinterpreted.
- Custom policies dispatch through a named-function registry, never through
  YAML-embedded code -- a deliberate security boundary given policy packs are meant
  to be swappable, deployer-supplied configuration.

**Current state:**
- Phase 3 Day 14 done and checked off. The AML pack is real and fires correctly at
  every trigger point Section 9.8 describes (except the two named, documented
  narrowings). Day 15 (Spark analytics + the scripted end-to-end demo) is the last
  remaining Phase 3 gate item.

**Next steps:**
1. Day 15 -- Spark synthetic telemetry (10M records) + aggregation job + populated
   Grafana dashboards + the scripted end-to-end demo
   (`interpose demo aml --setup && --run`), wiring `run_investigation.py` into the
   Typer CLI for the first time.
2. Consider whether the investigation agent should run against the real ~150MB
   subsampled dataset (not just fixtures) in a manual live-verify pass once Day 15's
   demo script exists, to see real-scale tool-call volume.

**Loose ends / reminders:**
- None new this session.

---

## 2026-07-30 — Phase 3 Day 13: AML investigation agent, an OFFSET bug, a real Groq run

**What happened:**
- Closed a loose end from a prior session first: `docs/project/WORKING_CONVENTIONS.md`
  had been written but never committed. Branched, committed, opened PR #11, waited for
  CI, squash-merged -- its own small unit of work, separate from today's real focus.
- Built the AML investigation agent (`agents/aml-investigator/`), Phase 3 Day 13 per
  `docs/ROADMAP.md`: a *client* of Interpose, not part of it -- explained in the new
  `concepts/30-client-agents-vs-control-plane-agents.md`, alongside why it's a linear
  5-node graph (Discovery → Enrichment → Assessment → Recommendation → Report) rather
  than a ReAct loop.
- `aml_investigator.gateway_client.InvestigationClient`: two real `ClientSession`s (one
  per upstream route) through the live gateway, recording every call (ok/error) to a
  `call_log` for the integration test to inspect.
- Discovery/Enrichment nodes: pure tool-calling, no LLM. Assessment/Report nodes reuse
  `interpose.control_plane.llm.generate_structured` (Groq) rather than a second
  wrapper -- a deliberate exception to `mcp-servers/`'s zero-`interpose`-dependency
  rule, since this agent has no independent-third-party fiction to protect. Both LLM
  nodes have a deterministic fallback on `LLMError`, same discipline as Agent A3's
  HITL narrative (Day 8).
- Seed alert generator (`aml_investigator.seed.pick_seed_alert`) queries the real
  subsampled Parquet directly via DuckDB for a real labeled-laundering account, no
  dependency on the transaction-graph server's own tools (which don't expose
  `is_laundering` as a filter, by design -- that's the answer the agent investigates
  toward, not starts from).
- **Two real bugs found by this module's own tests, before either shipped:**
  (1) the seed generator's first version used a fixed `OFFSET (seed % 97)`, which only
  works by accident against the real dataset's 35,230 laundering rows and returned
  nothing against a 2-3-row test fixture -- fixed by bounding the offset to the real
  candidate count (`seed % count(*)`) instead of a number tuned to one dataset's size.
  (2) Enrichment originally fetched `get_entity_detail` for *any* sanctions-check
  result, but `check_entity` always returns its single best candidate whether or not
  it clears the match threshold -- fixed to gate on `is_match`, caught by a unit test
  before it ever reached the live integration run.
- 31 new tests: 24 unit (fake gateway client, fake LLM, no network or API key) plus 2
  new live integration tests (`tests/integration/test_investigation_agent.py`) driving
  the full graph through a real gateway + real `ofac-sanctions` + real
  `transaction-graph` servers (all three as live subprocesses, fixture data via a new
  `aml_investigator_stack` conftest fixture). 237 total tests green, `ruff` clean.
- **Live-verified a second way, beyond the automated suite**: ran
  `agents/aml-investigator/run_investigation.py` by hand against the same fixture
  stack, but with this repo's real `.env` `GROQ_API_KEY` -- a genuine Groq call
  produced a valid `Assessment` and `InvestigationReport`, both validating against
  their strict JSON schemas on the first try (no fallback triggered), correctly
  recommending `escalate` on the fixture's seeded structuring pattern and recording it
  via a real `mark_investigated` write.

**Decisions made:**
- Investigation agent reuses `interpose.control_plane.llm.generate_structured`
  directly rather than a second LLM wrapper -- explained in concept 30.
- New `agents` uv dependency group (`duckdb`), isolated the same way as `analytics`/
  `mcp-servers`, since only the seed generator needs it.
- `agents/aml-investigator/src` added to pytest's `pythonpath` list, but as one real
  importable package (`aml_investigator`), not bare top-level modules -- avoids the
  cross-server module-name collision the existing `mcp-servers` pythonpath entries
  already have to work around (see `pyproject.toml`'s own comment on that).

**Current state:**
- Phase 3 Day 13 done and checked off in `docs/ROADMAP.md`. The investigation agent
  runs its full flow end-to-end through the real gateway, with a real LLM, on fixture
  data. Day 14 (the 7-policy AML pack) and Day 15 (Spark analytics + full demo script)
  are the remaining Phase 3 gate items.

**Next steps:**
1. Day 14 — AML policy pack (`policies/packs/aml/`, all 7 policies per Section 9.8),
   including the two custom Python policies (`aml-sanctions-required`,
   `aml-structuring-alert`). Test: policy fires at expected trigger points during a
   full investigation run through this agent -- including, for the first time, an
   actual HITL hold-and-resume on `mark_investigated` via `aml-write-hitl-gate.yaml`.
2. Day 15 — Spark synthetic telemetry (10M records) + aggregation job + populated
   Grafana dashboards + the scripted end-to-end demo
   (`interpose demo aml --setup && --run`) with a real HITL cycle. This is also where
   `run_investigation.py` gets wired into the Typer CLI.
3. Consider running the investigation agent against the *real* subsampled dataset (not
   just fixtures) once Day 14's pack exists, to see real-scale tool-call volume
   (Section 9.7's ~40-60 calls, vs. the ~7 the small fixture graph produces).

**Loose ends / reminders:**
- The Kaggle API token pasted into an early chat message should still be rotated
  (Settings → API → regenerate) -- flagged again, still not confirmed done. Asked the
  owner directly this session rather than silently dropping it.

---

## 2026-07-28 — Phase 3 Day 12: transaction-graph MCP server, a VARCHAR bug and an unpinned-dependency bug

**What happened:**
- Built `mcp-servers/transaction-graph/`, the second AML MCP server (Section 9.6),
  following the same standalone-service pattern Day 11 established for
  `ofac-sanctions`: its own `Dockerfile`, own tiny `Settings`, no dependency on
  `src/interpose/`. Six tools: `query_transactions`, `get_account` (live summary
  stats, computed on every call since the dataset itself has none), `neighbors`
  (breadth-first k-hop counterparty walk), `subgraph` (the induced subgraph over a
  requested account set), `structuring_check` (a canned structuring/"smurfing"
  heuristic), and `mark_investigated` (the one write tool).
- Data source is the Spark-subsampled IBM AML Parquet from Phase 0
  (`data/README.md`) — loaded as two DuckDB *views* (`read_parquet(...)`, filters
  pushed down into the scan, no separate "load" step) plus one real, in-memory,
  per-restart-ephemeral table (`investigated`) for the write path. New concept file,
  `concepts/29-embedded-analytics-with-duckdb.md`: embedded-vs-server database
  tradeoffs (DuckDB vs. Postgres), reading Parquet without loading it, the
  single-writer lock around the one write path, and the design reasoning behind
  `neighbors`' BFS-over-recursive-CTE choice, `subgraph`'s induced-subgraph
  semantics, and `structuring_check`'s window anchored to the account's own last
  activity rather than wall-clock (this is 2022 data).
- `store.py`'s query functions take a plain `GraphStore` + arguments, fully decoupled
  from FastMCP/`Context` — all 16 new unit tests
  (`tests/unit/mcp_servers/test_transaction_graph_store.py`) run against a tiny
  in-memory fixture table (a synthetic 2-hop chain plus a seeded structuring
  pattern), no files, no server process. 7 new integration tests
  (`tests/integration/test_gateway_transaction_graph.py`) drive real tool calls
  through the actual live gateway, via a new `transaction_graph_upstream_and_gateway`
  fixture pointed at small local CSV fixtures
  (`mcp-servers/transaction-graph/tests/fixtures/`, synthetic data — this dataset's
  CDLA-Sharing-1.0 license is share-alike, so fixtures here are synthetic rather than
  small real extracts the way OFAC's public-domain fixtures could be). Added
  `duckdb` to the `mcp-servers` uv dependency group; `config/upstreams.yaml` gained a
  `transaction-graph` route (port 9003).
- **Two real bugs found via this project's own testing, not assumed:**
  1. DuckDB's `read_csv_auto` (used only by the small test-fixture CSVs) infers
     numeric-looking ID columns like `bank_id: "1"` as INTEGER — but the real Parquet
     data is always string-typed (Spark's `.csv(header=True)` read has no schema
     inference, so `bank_id` etc. stay strings). `AccountRecord`'s `bank_id: str`
     Pydantic validation caught the mismatch immediately (`get_account` failed with a
     validation error) the first time the server actually ran against the fixture.
     Fixed by explicitly `CAST`ing every ID-shaped column to VARCHAR in both view
     definitions, regardless of source — a defensive fix that also protects the real
     Parquet path, not just the fixture.
  2. Building the Docker image failed outright:
     `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. The Dockerfile
     installs `mcp[cli]>=1.28.1` — a lower bound only, no lockfile (standalone
     service Dockerfiles deliberately don't share the root project's `uv.lock`).
     Between Day 11 (when `ofac-sanctions`' identical pattern last built clean) and
     today, upstream shipped a breaking `mcp==2.0.0` that renamed/removed
     `mcp.server.fastmcp`. Fixed by pinning the exact version the root project's
     `uv.lock` already resolved (`mcp[cli]==1.28.1`) in *both* this Dockerfile and
     `ofac-sanctions/Dockerfile` — the latter had the identical latent bug, silently
     armed and unnoticed until a fresh rebuild.
- **Live-verified twice**: once via `uv run pytest` (208 total tests green, `ruff`
  clean) against the real gateway with fixture data; once as a genuine Docker
  container, built from the fixed Dockerfile and run with the real ~150MB subsampled
  dataset bind-mounted in (`docker run -v ~/.interpose/data/ibm-aml:/data/ibm-aml:ro
  ...`) — startup log confirmed `transactions=3158483 accounts=500000`, matching
  `subsample_report.json` exactly, and a real `get_account`/`neighbors`/
  `structuring_check` call against a genuine high-volume account (`70:100428660`,
  294K transactions) returned correct, real results.

**Decisions made:**
- DuckDB reads Parquet/CSV directly as views rather than importing data into its own
  storage — matches how the real ~150MB dataset should be queried (no redundant copy)
  and lets small CSV fixtures substitute transparently for tests.
- `mark_investigated`'s state is a real, ephemeral, in-memory table (not Postgres) —
  matches Section 9.6's explicit "state is ephemeral and reset per demo run"; the
  durable record of the write action is the audit log the gateway produces around the
  call, not this table.
- Pinned `mcp[cli]==1.28.1` in both AML MCP server Dockerfiles rather than leaving
  either on a lower-bound-only constraint — standalone service Dockerfiles have no
  lockfile of their own, so an unpinned dependency is a live reproducibility risk, not
  just a hypothetical one (it broke a build today).

**Current state:**
- Phase 3 Day 12 is done and checked off in `docs/ROADMAP.md`. Both AML MCP servers
  (OFAC sanctions, transaction-graph) now exist, are independently containerized, and
  proxy real tool calls through the live gateway.
- **Named gap, deliberately not done today:** neither AML server is deployed into the
  local `kind` cluster yet (`dev/mcp-servers/` only has `hello-echo` so far).
  Transaction-graph's real dataset would need `kind.yaml`'s `extraMounts` to
  bind-mount `~/.interpose/data/ibm-aml/` into the cluster nodes — not added
  speculatively; deferred to whenever Day 13's investigation agent actually needs a
  real in-cluster run.

**Next steps:**
1. Day 13 — the AML investigation agent (LangGraph client): a 5-node flow (Section
   9.7) that picks a seeded suspicious account, drives Discovery/Assessment/Report
   Composer nodes calling both AML MCP servers' tools through the gateway, ~40 tool
   calls end-to-end (minus HITL, which needs Day 14's policy pack first).
2. Day 14 — the AML policy pack (7 policies, Section 9.8), including the custom
   `aml-sanctions-required` and `aml-structuring-alert` policies and the
   `aml-write-hitl-gate` that gates `mark_investigated` specifically.
3. Revisit the deferred kind/`extraMounts` deployment once an in-cluster run is
   actually needed (Day 13 or later), rather than before.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) — flagged again, still not confirmed done.

---

## 2026-07-27 (cont'd 2) — Phase 3 Day 11: OFAC sanctions MCP server, real data quirks + a real fuzzy-matching bug

**What happened:**
- Started Phase 3 (AML Pack) at its natural entry point, Section 14.7's Day 11: the
  OFAC sanctions MCP server.
- Before writing any code, checked what Phase 0 actually downloaded vs. what Section
  9.6 assumes: only `sdn.csv` existed locally, but `check_alias` ("alias-aware
  search -- SDN entries often list multiple names") needs a second Treasury file,
  `alt.csv` (Alternate Identities), which wasn't downloaded. Fetched it fresh from
  the same `sanctionslistservice.ofac.treas.gov` API (20,159 real rows) -- without
  it, `check_alias` would just be `check_entity` under a different name.
- Discovered and documented the real shape of both files (`data/README.md`'s new
  "OFAC file formats" section): no header row in either; `-0-` as a general null
  sentinel, including for `sdn_type`, where blank means "entity" (business/
  organization), not "unknown" -- only `individual`/`vessel`/`aircraft` are ever
  spelled out explicitly; multiple sanctions programs joined as
  `PROGRAM1] [PROGRAM2` with no enclosing brackets, not a normal delimiter; and the
  live API's export is UTF-8 (many tutorials assume Windows-1252, a fact worth
  checking rather than trusting).
- Built `mcp-servers/ofac-sanctions/` as its own small standalone service (own
  `Dockerfile`, own tiny `Settings`, no dependency on `src/interpose/`) --
  deliberately mirrors how a real production sanctions-screening API would relate to
  the gateway: an external system Interpose proxies to, not something the gateway
  owns. Three tools: `check_entity` (fuzzy-match against SDN primary names only,
  filtered by entity type), `check_alias` (fuzzy-match against primary names *and*
  every alias, any type), `get_entity_detail`. `loader.py`'s parsing/matching
  functions are pure (no network), unit-tested directly; `server.py` wires them into
  a FastMCP app whose lifespan fetches both files fresh on startup by default
  (`OFAC_SDN_SOURCE`/`OFAC_ALT_SOURCE` override to a local file, same "real by
  default, overridable for tests" shape as the rest of this project's Settings).
- **Found a real, non-obvious bug via this project's own tests**: `rapidfuzz`'s
  default scorer (`fuzz.WRatio`) is case-sensitive, and the SDN list is all-caps by
  Treasury convention. A realistically-cased query ("Aerocaribbean Airlines")
  scored its own correct match at ~14% -- literal character-case mismatches read as
  dissimilarity -- and lost to several unrelated candidates in the same list. Fixed
  by passing `rapidfuzz.utils.default_process` (lowercases + normalizes) as the
  `processor` on every match call; the same query now scores a perfect 100. The
  first version of the code "worked" (no crash, returned a score) while being
  silently wrong -- caught because a unit test used realistic mixed-case input
  instead of the dataset's own casing.
- Added a new uv dependency group, `mcp-servers` (`rapidfuzz`), isolated from the
  core gateway install the same way `analytics` (pyspark) already is -- a bare
  `interpose` install has no use for it. Updated CI's `test` job to
  `--group mcp-servers` alongside `--dev`.
- 13 new unit tests (`tests/unit/mcp_servers/test_ofac_loader.py`, pure
  parsing/matching against real public-domain fixture rows, no network) plus 4 new
  integration tests (`tests/integration/test_gateway_ofac.py`) driving real
  `check_entity`/`check_alias`/`get_entity_detail` calls through the actual gateway
  -- a new `ofac_upstream_and_gateway` fixture in `tests/integration/conftest.py`,
  pointed at small local fixture CSVs (`mcp-servers/ofac-sanctions/tests/fixtures/`,
  4 real SDN entries + 1 real alias) so the suite never depends on Treasury being
  reachable. Along the way, learned a real FastMCP quirk worth documenting: a tool
  returning a Union type (`SanctionsMatch | None`) wraps `structuredContent` under a
  `"result"` key; a tool returning a single concrete model (`SDNEntry`) doesn't --
  an integration test that assumed one shape for both failed until this was
  understood, not guessed around.
- **Live-verified twice, not just via the fixture-based automated suite**: first, a
  bare container hitting the real, live Treasury API end-to-end -- log confirmed
  `entries=19157 aliases=20159` loaded (D-2's "10,000+ SDN entries" shipped-when
  criterion, met for real), and a real MCP client got a genuine 100%-confidence
  match back. Second, the same real-data check driven through the actual gateway's
  `/mcp/ofac-sanctions` route (via the fixture-CSV path, for a fast/reproducible
  check).
- Added `concepts/28-fuzzy-matching-and-sanctions-screening.md`: why exact-match
  search doesn't work for this domain, rapidfuzz basics, the case-sensitivity bug as
  a worked example, why `check_entity`/`check_alias` deliberately search different
  corpora, and the `structuredContent` envelope quirk.
- 185 total tests green (168 + 13 unit + 4 integration), `ruff check .` clean.

**Decisions made:**
- `mcp-servers/ofac-sanctions/` is its own standalone service (own Dockerfile, own
  Settings, flat module imports via `pythonpath` in `pyproject.toml` rather than
  package machinery) -- not a module under `src/interpose/`, and not folded into any
  existing image. Matches Section 6.16's module boundary and previews how Phase 3's
  `transaction-graph` server should be structured too.
- `rapidfuzz` isolated to its own `mcp-servers` uv dependency group, not a core
  dependency -- the gateway itself never needs it.

**Current state:**
- Phase 3 Day 11 is done. The OFAC sanctions MCP server is real, tested, and
  live-verified against the actual Treasury API and the actual gateway.

**Next steps:**
1. Day 12 — the transaction-graph MCP server: DuckDB embedded with the subsampled
   IBM AML data (already prepared in Phase 0), six tools per Section 9.6
   (`query_transactions`, `get_account`, `neighbors`, `subgraph`,
   `structuring_check`, `mark_investigated` -- the one write tool, which exists
   solely to demonstrate HITL gating later in Day 14). Introduce DuckDB as a new
   concept when this starts.
2. Day 13 — the AML investigation agent (single-agent LangGraph client of
   Interpose, distinct from Interpose's own multi-agent control plane).
3. Day 14 — the real 7-policy AML pack (this is when `pii_redaction`'s
   `NotImplementedError` stub and a response-side policy hook both need to become
   real, per this session's adversarial-suite gap notes from Day 10).
4. Day 15 — Spark telemetry + full AML demo end-to-end.
5. Commit/push/PR/merge this session's Day 11 work per the established per-day
   cadence before starting Day 12.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  -- flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented.
- Phase 2's one open gate clause (a real HITL approve cycle through the
  kind-deployed gateway specifically) is still open -- OFAC's own server isn't
  wired into `dev/mcp-servers/`/kind yet either; both are natural to close once
  Phase 3's servers are being deployed in-cluster for the full AML demo (Day 15).

---

## 2026-07-27 (cont'd) — Phase 2 Day 10: README quickstart, adversarial skeleton, real OpenTelemetry trace

**What happened:**
- Merged the echo-in-cluster work from earlier this session as PR #7 (squash-merged
  after CI -- `lint`/`helm`/`test` -- all passed), then continued straight into Day
  10's remaining scope.
- **README quickstart**: added a `## Quickstart` section to the root `README.md` with
  both real paths -- bare `uv run` (docker-compose Postgres/Redis, `alembic upgrade
  head`, gateway + echo server as background processes, `interpose verify-audit`/
  `review list`) and the kind path (`scripts/dev-up.sh`/`dev-down.sh`). Ran the bare
  path command-by-command before committing it, not just written from memory.
- **Adversarial test suite skeleton** (`tests/adversarial/`, Section 10.5/G9):
  `schema.py` (Pydantic `AdversarialScenario`/`ToolCallStep`/`ExpectedOutcome`, the
  latter validated against the real `interpose.audit.models.STATUSES` tuple rather
  than a duplicated literal), `attack_classes.py` (a registry of the 6 required attack
  classes, each tagged with its defense mechanism and, distinctly, whether what's
  missing is "just a scripted fixture" -- for the 4 classes whose enforcement already
  exists -- or a real gateway capability, for the 2 that don't: a response-side policy
  hook, and a real `pii_redaction` beyond its current `NotImplementedError` stub),
  `generate.py` (JSONL read/write machinery; `generate()` itself raises
  `NotImplementedError` naming the gap, for every class, on purpose). 9 new tests
  assert this "skeleton, zero real scenarios" state directly rather than leaving it
  as a comment -- including one confirming the registry covers exactly the 6 G9
  classes, so silently adding/renaming one without updating the registry would fail
  CI.
- **First real distributed trace** (Section 11.8, gate S3 -- "render a trace of a
  single tool call end-to-end"). Added `opentelemetry-sdk` +
  otlp-grpc/fastapi/httpx/sqlalchemy instrumentation packages, a
  `otel_exporter_endpoint` setting (`None` default, same opt-in shape as
  `groq_api_key`), and `interpose.observability.tracing`: auto-instrumentation gets
  three real spans for free (FastAPI root span per request, httpx child span for the
  forward call to the upstream MCP server, SQLAlchemy child spans for the audit
  writes), plus one hand-written span around policy evaluation (`_compile_and_evaluate`
  in `app.py`) since that's pure in-process logic nothing auto-instruments. Jaeger
  (`jaegertracing/all-in-one:1.60` -- `:1.65` doesn't exist, verified via `docker
  manifest inspect` before settling on a real tag) added to `docker-compose.yaml` as
  the local OTLP receiver + UI, opt-in only, not wired into the Helm chart yet (named
  gap, `charts/interpose/README.md` updated).
- **Real bug found and fixed via live verification, not by inspection.** First live
  check (gateway + echo server + Jaeger up, one real `echo` call, then queried
  Jaeger's HTTP API directly) showed spans landing but every single one as its own
  disconnected one-span trace -- nothing nested under a request root. Root cause:
  `FastAPIInstrumentor.instrument_app()` works by monkeypatching
  `Starlette.build_middleware_stack`, which Starlette only calls once and caches the
  result of, on the app's very first ASGI event -- and the gateway's lifespan startup
  *is* that first event. Calling `instrument_app()` from inside the lifespan (as
  first written) patches the method after the cache already holds the unpatched
  middleware stack, so the patch never takes effect. Fix: split `tracing.py` into
  `setup_tracing()` (must run immediately after `FastAPI(...)` is constructed, before
  the lifespan) and `instrument_sqlalchemy_engine()` (runs inside the lifespan once
  the engine exists -- no such ordering constraint). Re-verified after the fix: one
  16-span trace for the `echo` call (root HTTP span -> `policy.evaluate` -> audit
  writes -> httpx forward -> more audit writes, all correctly parented) and a 9-span
  trace for `dangerous_tool` that correctly stops after the DENY decision with no
  upstream-forward span at all -- both confirmed by querying Jaeger's `/api/traces`
  directly, not by trusting the UI would show something.
- Updated `charts/interpose/README.md`'s named-gaps table (OTel collector/Jaeger
  in-cluster is now its own explicit row, and the Prometheus row's wording no longer
  implies tracing is unbuilt), added `concepts/27-opentelemetry-and-distributed-
  tracing.md` (spans/traces/OTLP, why auto-instrumentation, and an explicit callout
  that this is unrelated to `audit_entries`' own `trace_id`/`span_id` UUID columns --
  same words, two unrelated systems, worth keeping straight).
- Full suite: 168 tests green (159 + 9 new adversarial-skeleton tests), `ruff check .`
  clean throughout.

**Decisions made:**
- Dev-fixture MCP servers and the OTel/Jaeger trace backend both stay opt-in /
  outside the Helm chart for now -- same reasoning each time: nothing in-cluster
  exercises them yet, and wiring them in speculatively would mean untested chart
  surface area, not a stronger deploy.
- The adversarial suite's `generate()` raises `NotImplementedError` uniformly today,
  even for the 4 attack classes whose enforcement already exists -- writing templates
  ahead of a harness that actually runs them through a live gateway would be untested
  prose regardless of whether the policy engine is ready.

**Current state:**
- **Phase 2 Day 10 is done.** All four planned items landed: CI-green confirmation,
  README quickstart, adversarial fixture-generator skeleton, first real Jaeger trace.
  Phase 2's overall gate is substantially met (see `docs/ROADMAP.md`'s new status
  note) with one clause left deliberately open: a HITL hold-and-approve cycle hasn't
  been driven through the kind-deployed gateway specifically yet (only via
  docker-compose, Day 6) -- a natural fit for early Phase 3 rather than a Day 10 gap.

**Next steps:**
1. Commit/push/PR/merge this session's second chunk of work.
2. Start Phase 3 (AML Pack): OFAC sanctions MCP server, transaction-graph MCP server
   (DuckDB over the subsampled AML data), the LangGraph investigation agent, the real
   7-policy AML pack, the Spark telemetry/aggregation job. `dev/mcp-servers/` gets its
   first non-toy entries here.
2. Optionally, early in Phase 3: drive one real HITL approve cycle through the
   kind-deployed gateway (`hello-echo-hitl.yaml`'s `hitl_tool` is already deployed) to
   close Phase 2's one open gate clause, before or alongside standing up the real AML
   servers.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) -- flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented -- same
  gap noted since Day 4.
- No automated kind-based deploy test in CI yet -- still a named Phase 4 gap.
- No OTel Collector/Jaeger in the Helm chart yet -- traces only work for bare/
  docker-compose dev today; a kind deployment has `otel_exporter_endpoint` unset and
  traces nothing.

---

## 2026-07-27 — Phase 2 Day 10 (partial): echo server deployed in-cluster, real end-to-end kind test

**What happened:**
- Resolved the open question from Day 9's next-steps: deployed
  `examples/hello-mcp-http-echo` inside the kind cluster as a real upstream, rather
  than leaving that gap open until Phase 3's real AML MCP servers arrive.
- Deliberate scoping call: the echo server is a plain `kubectl apply -f
  dev/mcp-servers/` fixture (`dev/mcp-servers/hello-echo.yaml`, new directory), not a
  `charts/interpose/` template. The chart's job is the actual product (gateway +
  control plane + its infra); the echo server stands in for a future *external* MCP
  server, which is exactly how Phase 3's real servers will relate to the gateway too
  -- something the chart routes to, not something it owns.
- `server.py` now reads host from `MCP_ECHO_HOST` (default unchanged at `127.0.0.1`,
  so the existing subprocess-based integration tests and bare `uv run` usage are
  untouched) -- same fix shape as the gateway's own `GATEWAY_HOST` from Day 9,
  needed because nothing outside a container's network namespace can reach
  `127.0.0.1`.
- Added `examples/hello-mcp-http-echo/Dockerfile`: a small standalone image (just
  `mcp[cli]`, non-root), deliberately not folded into the main `interpose:dev` image
  -- the fixture needs none of the gateway's dependencies (Postgres, Redis,
  LangGraph, ...), so bundling it in would ship unrelated weight for something that
  isn't the app under test.
- `scripts/dev-up.sh`: builds and `kind load docker-image`s both `interpose:dev` and
  the new `hello-echo:dev`, applies `dev/mcp-servers/` right after namespace creation
  (before the Helm install), and waits on the fixture's Deployment condition before
  printing pod status.
- `charts/interpose/values-dev.yaml` now sets
  `upstreams.servers.hello-echo.url` to the in-cluster Service's cluster-DNS name
  (`hello-echo.interpose-system.svc.cluster.local:9001`) -- `values.yaml`'s own
  commented-out example from Day 9 is what this replaces, now that it's real instead
  of speculative.
- Updated the now-stale "no MCP server deployed in-cluster" comments in
  `values.yaml`/`configmap-upstreams.yaml`, `charts/interpose/README.md`'s install
  snippet and deploy-list, `examples/hello-mcp-http-echo/README.md`, and added a new
  section to `concepts/26-helm-and-the-interpose-chart.md` covering the chart-vs-
  fixture boundary and Kubernetes Service DNS (`<service>.<namespace>.svc.cluster.local`)
  as the reason a Service name, not a pod IP, is what gets configured.
- **Live-verified against a real kind cluster** (`scripts/dev-up.sh`, 149s up):
  a genuine MCP client (not curl -- streamable-HTTP needs a real
  `initialize`/`list_tools`/`call_tool` handshake) run through the deployed gateway
  at `http://127.0.0.1:8000/mcp/hello-echo` got a real `echo` tool result back, and
  `dangerous_tool` was denylisted for real by the same policy that already worked in
  docker-compose. Confirmed via `kubectl exec ... psql` against the actual in-cluster
  Postgres: an INTENT/COMPLETED pair for `echo`, one DENIED row for `dangerous_tool`
  with the correct `policies_fired`, in the real hash-chained table -- not a stub.
  `scripts/dev-down.sh` left no residual state, as before.
- Full local integration suite (26 tests) re-run before touching kind, to confirm the
  `server.py` host-override change didn't regress the existing docker-compose/
  subprocess path; 159 total tests green afterward, `ruff check .` clean,
  `helm lint`/`helm template` both clean.

**Decisions made:**
- Dev-fixture MCP servers live in `dev/mcp-servers/` as plain manifests, never as
  chart templates -- matches how a real external MCP server (Phase 3's OFAC /
  transaction-graph servers) will actually relate to the gateway.
- Each fixture gets its own minimal Dockerfile/image rather than reusing or extending
  the main `interpose:dev` image, to keep "what the product depends on" and "what a
  test fixture depends on" from blurring together.

**Current state:**
- Phase 2 Day 10 is partially done -- the echo-server decision from Day 9 is resolved
  and live-verified, but Day 10's other original scope (confirm CI-green for Week 1+2
  integration tests, README quickstart draft, first Jaeger trace, adversarial
  fixture-generator skeleton) is still open.

**Next steps:**
1. Finish Day 10: confirm the full suite is green in CI (not just locally), draft the
   README quickstart, get a first distributed trace visible in Jaeger, and build the
   adversarial test suite skeleton (fixture generator only, no attacks yet).
2. Commit/push/PR/merge this session's work per the established per-day cadence.
3. After Day 10's gate closes, Phase 3 (AML Pack) starts: OFAC sanctions MCP server,
   transaction-graph MCP server, the LangGraph investigation agent, the real 7-policy
   AML pack, and the Spark telemetry job -- at which point `dev/mcp-servers/` gets a
   second, non-toy entry.

**Loose ends / reminders:**
- The Kaggle API token pasted into an earlier chat message should still be rotated
  (Settings → API → regenerate) -- flagged again, still not confirmed done.
- Postgres append-only role enforcement (Section 10.7) still not implemented -- same
  gap noted since Day 4.
- No automated kind-based deploy test in CI yet (only `helm lint`/`helm template`) --
  still a named Phase 4 gap, not required for Day 10.

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
