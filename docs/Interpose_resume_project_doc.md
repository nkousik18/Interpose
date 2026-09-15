# Interpose — Project Documentation (Resume Source of Truth)

---

## 1. Project Summary

Interpose is an MCP (Model Context Protocol) audit/policy gateway: a transparent proxy that sits between AI agents and the real tool servers they call, so that every tool invocation an agent makes — read or write — passes through one governance point regardless of which agent framework built the caller or which team owns the upstream server. For every call it evaluates a composable policy engine (8 effect types: allowlist, denylist, rate-limit, PII redaction, human-in-the-loop gate, custom Python hooks, tag-only, cost-cap), writes a SHA-256 hash-chained, tamper-evident audit record before and after forwarding, and — asynchronously, off the gateway's hot path — runs a 5-agent LangGraph control plane that enriches each decision with a session risk score, flags statistical anomalies, composes human-readable evidence for reviewers, and promotes repeated-denial patterns to durable incident records. A full Kubernetes deployment (Helm chart, 23 templates) runs the whole stack — gateway, Postgres audit store, Redis session/HITL state, an OTel Collector + Prometheus feeding 4 Grafana dashboards — against a local `kind` cluster, with a hand-rolled Terraform module (49 AWS resources across 15 files: VPC, EKS, RDS, ElastiCache, S3, IRSA, KMS, CloudWatch) built and statically validated for a real AWS reference deployment.

The project's worked example is anti-money-laundering (AML) investigation: two real, standalone MCP servers (`ofac-sanctions`, backed by the live U.S. Treasury sanctions list — 19,169 entries; `transaction-graph`, backed by a 500,000-account, 3.16M-transaction subsample of the IBM AML Kaggle dataset, DuckDB-queried over Parquet) sit behind the gateway, governed by a real 6-policy AML pack (agent-scoped sanctions-check precondition, mandatory HITL gate on every write, blanket PII redaction, rate limiting, structuring-pattern detection, compliance audit tagging). A separate client-side investigation agent (`agents/aml-investigator`, a 5-node linear LangGraph, distinct in shape and purpose from the gateway's own control plane) drives a real, end-to-end investigation through the gateway — real sanctions matches, real HITL approval cycles, real Groq LLM calls for narrative synthesis, and a real chain-verified audit trail as the output. Every major subsystem was live-verified against a real running system, not just unit-tested: real Treasury API calls, real Groq API calls, real `kind` clusters, real Grafana dashboards queried through their own `/api/ds/query` endpoint, real `terraform validate` runs, a real Terraform-schema bug caught before ever touching AWS, and a real Prometheus histogram bug caught only by computing a live `histogram_quantile()` against real scraped data.

327 tests (260 unit, 45 integration, 22 live adversarial), an adversarial test suite proving defense against all 6 required attack classes end-to-end through a real gateway, a reusable eval harness producing a JSON evaluation report as a CI artifact, and 37 numbered concept documents (`concepts/00` through `concepts/36`) written alongside the code as a deliberate, ongoing learning record — this is a project built to demonstrate real, first-principles understanding of MCP, Kubernetes, Terraform, Spark, LangGraph multi-agent orchestration, and observability infrastructure, not to abstract any of them away behind someone else's framework on day one.

**Status as of the most recent session (2026-08-17): Phases 0-3 complete, Phase 4 (Proof & Polish) in progress** — the adversarial suite (Day 16) and the Terraform module (Day 17, statically validated only) are done; blog posts, demo video, the v0.1.0 tag, and a live `terraform apply` against real AWS remain.

---

## 2. Tech Stack

| Component | Technology | Version | Rationale |
|---|---|---|---|
| Language / package manager | Python + `uv` | Python ≥3.12 | `uv` for fast, reproducible dependency resolution; `hatchling` build backend |
| Gateway HTTP surface | FastAPI + Uvicorn | fastapi ≥0.115, uvicorn[standard] ≥0.32 | Async-native, streaming-response support for the MCP transport's long-lived GET |
| MCP protocol | MCP Python SDK | mcp[cli] ≥1.28.1 | The reference implementation; pinned exactly (not `>=`) in every standalone server's own Dockerfile after a real breaking-upstream-release bug (§20) |
| Policy/config validation | Pydantic + pydantic-settings | ≥2.5 | Discriminated-union policy schema; typed settings from env vars |
| Database | PostgreSQL + SQLAlchemy (async) + Alembic | postgres:16, sqlalchemy[asyncio] ≥2.0, psycopg[binary] ≥3.1, alembic ≥1.13 | Audit log + control-plane + analytics tables; migrations as a version-controlled paper trail |
| Session / HITL state | Redis | redis:7.4-alpine, redis-py ≥5.0 | Ticket queue, rate-limit counters, session risk-score cache |
| Multi-agent orchestration | LangGraph | ≥0.2 | Stateful graph with conditional edges — matches the control plane's real shape (dispatch → enrich → maybe escalate), not a linear chain or open-ended ReAct loop |
| LLM provider | Groq | groq ≥0.11 | Genuine free tier for a learning project; provider-swappable by design (Anthropic Claude is the eventual production default per the scoping doc) |
| Distributed tracing | OpenTelemetry SDK + OTLP exporter | opentelemetry-sdk ≥1.27 | FastAPI/httpx/SQLAlchemy auto-instrumentation + one manual span for policy evaluation |
| Metrics | OpenTelemetry Metrics API → OTel Collector → Prometheus | otel/opentelemetry-collector-contrib:0.111.0, prom/prometheus:v2.55.1 | Reuses the same OTLP pipeline as tracing rather than a second `prometheus_client` integration |
| Dashboards | Grafana | grafana/grafana-oss:11.4.0 | 4 dashboards, dual Postgres + Prometheus datasources |
| Trace backend (bare local dev) | Jaeger | jaegertracing/all-in-one:1.60 | No in-cluster trace backend yet (named gap) — bare dev only |
| Container orchestration | Kubernetes via Helm + `kind` | Helm chart v0.1.0, kind for local dev | 23 templates, embedded-vs-external toggle pattern applied 3× (Postgres/Redis, then OTel Collector/Prometheus) |
| Infrastructure as code | Terraform | ≥1.7 (CI pinned 1.7.5); aws ~>5.0, kubernetes ~>2.30, random ~>3.6, tls ~>4.0 | Hand-rolled AWS EKS reference module, 49 resources across 15 files — no community module dependency |
| Batch analytics | Apache Spark (PySpark) | pyspark ≥4.2.0 (dedicated `analytics` uv group) | Dataset subsampling (Phase 0) + synthetic telemetry generation/aggregation (Phase 3 Day 15) |
| Embedded OLAP | DuckDB | duckdb ≥1.1 | `transaction-graph` MCP server's query engine over Parquet — no external data warehouse needed |
| Fuzzy matching | RapidFuzz | rapidfuzz ≥3.10 | Sanctions-screening name matching; case-normalized after a real case-sensitivity bug (§20) |
| CLI | Typer | (via `interpose` entry point) | `verify-audit`, `review`, `demo aml` commands |
| CI/CD | GitHub Actions | — | 5 jobs: `lint`, `helm`, `terraform`, `test`, `adversarial` |
| Testing | pytest + pytest-asyncio | pytest ≥9.1.1, pytest-asyncio ≥0.24 | 327 tests; real subprocess/real-Postgres integration tests, no mocking of the systems under test |
| Linting | Ruff | ≥0.15.22 | Single linter for the whole repo, `ruff check .` in CI |

---

## 3. The Gateway Request Lifecycle (Data Plane)

`src/interpose/gateway/app.py` — one FastAPI app, one proxy route (`@app.api_route("/mcp/{server_name}", methods=["GET","POST","DELETE"])`), plus `GET /healthz` (liveness only — checks nothing external, so Kubernetes never restarts a healthy pod over a transient DB blip) and `GET /readyz` (real Postgres `SELECT 1` + real Redis `PING`, 503 if either fails).

**The real code path** (not the scoping doc's aspirational "9 numbered stages" — this is what's actually implemented):

1. **Ingress + parse**: request logged, body read, `JSONRPCMessage.model_validate_json` (malformed envelope → HTTP 400, still logged).
2. **Route resolution**: server name → upstream URL via `RoutingTable` (unknown server → 404, not audited — there's no `{server, tool}` pair to attach an entry to).
3. **`tools/call`-only governance**: `_extract_tool_call` returns `None` for every other MCP method (`initialize`, `list_tools`, `notifications/*`, the long-lived server-push GET stream) — those bypass policy and audit entirely and go straight to a streamed passthrough forward. Only the actual governed action (`tools/call`) enters the policy/audit path.
4. **Policy compile + evaluate**: `policy_engine.compile(server, tool)` → `PolicySet.evaluate`, wrapped in an OTel span (`policy.evaluate`), fail-closed to `DENY(reason="policy_engine_error")` on any exception. Real evaluation order: `allowlist → denylist → rate_limit → custom(request) → hitl_gate`.
5. **Terminal outcomes**:
   - **DENY** → `DENIED` audit row, `DecisionEvent` published to the control plane, JSON-RPC error `-32001` (`policy_denied`) returned.
   - **HOLD** → `HELD` audit row → real Redis HITL ticket opened → gateway **blocks** (async, other requests unaffected) on `hitl.wait_for_decision(timeout_seconds)`. Three sub-outcomes: timeout (`DENIED`, `-32004`), human denial (`DENIED`, `-32003`), or approval (proceeds exactly like PASS).
   - **PASS** → `INTENT` audit row written *before* forwarding (so a crash mid-forward still leaves a record of intent) → forward.
6. **Forward + response processing**: streaming passthrough for the common case; buffered read-parse-redact-reserialize (`_forward_buffered`) only when the compiled `PolicySet` actually has a response-side policy (`has_response_side_policies`) — every other call keeps the cheap streamed path. On success → `COMPLETED` row linked to the `INTENT`/`HELD` row via `parent_id`. On upstream failure or a response-side policy evaluation crash → `UPSTREAM_ERROR` row.
7. **Metrics + egress**: 5 OTel instruments recorded at each of the branches above (§11), response returned.

**Real audit statuses** (`src/interpose/audit/models.py::STATUSES`, enforced by a Postgres `CHECK` constraint): `INTENT`, `COMPLETED`, `DENIED`, `HELD`, `UPSTREAM_ERROR`.

**Agent identity**: extracted from an `Authorization: Bearer <token>` header (`_extract_agent_id`) — not real authentication, a stable identity string the policy engine and control plane correlate on.

---

## 4. Policy Engine

`src/interpose/policies/{schema,policyset,custom,redaction}.py`. **8 effect types**: `allowlist`, `denylist`, `rate_limit`, `pii_redaction`, `hitl_gate`, `custom`, `tag_only`, `cost_cap` (schema-only stub — raises `NotImplementedError` unconditionally if evaluated; the gateway has zero real LLM-cost visibility to enforce it against).

**The one non-obvious rule, load-bearing for two real bugs found this project (§20):** an `allowlist` policy on a server is an unconditional early return — `PolicySet.evaluate` checks it *first*, and a match returns `PASS` immediately, bypassing denylist/rate_limit/hitl_gate entirely for that tool, not just tools it doesn't cover. Writing even one allowlist policy for a server flips that whole server to default-deny for everything not explicitly listed.

**Response-side (Stage 8) policies** — `pii_redaction` (accumulates redactions across multiple matching policies in one pass) and response-stage `custom` policies (tag the audit entry, **cannot** deny an already-completed call — a documented architectural boundary, not an oversight, confirmed against real precedent in §10).

**Real PII regex patterns** (`redaction.py`): `ssn` = `\b\d{3}-\d{2}-\d{4}\b`; `credit_card` = `\b\d(?:[ -]?\d){12,15}\b`; `bank_account` = `\b\d{9}[ -]?\d{4,17}\b` (a full routing+account combo, not a bare routing number — those are public per-bank identifiers).

**24 real policy YAML files across 4 directory trees** (deliberately duplicated, not shared, for isolation — see §15's design mistake):

| Tree | Count | Purpose |
|---|---|---|
| `config/policies/` | 4 | Bare local dev demo (denylist, 2× hitl_gate, rate_limit) |
| `policies/packs/aml/` | 6 + manifest | The real AML pack (§10) |
| `charts/interpose/files/policies-{hello-echo,aml}/` | 4 + 6 | Checked-in Helm chart copies, kept in sync by a dedicated test (`test_chart_policy_sync.py`) since Helm's `.Files.Glob` can't read outside the chart directory |
| `tests/adversarial/fixtures/policies/<attack_class>/` | 6 (1 each) | Fully isolated per-attack-class packs (§14) |

---

## 5. Hash-Chained Audit Log

`src/interpose/audit/{models,chain,store}.py`. Every audit entry carries `prev_hash`/`this_hash` (SHA-256 over canonical JSON of the entry's own fields), chained from a fixed genesis hash — `interpose verify-audit` walks the full chain and reports the first tampered entry, if any, regardless of any `--since` filter (a filter narrows the *report*, never the verification scope, since the tamper-evidence guarantee doesn't hold over an arbitrary slice).

**Concurrency**: writes are serialized via a Postgres advisory lock (`pg_advisory_xact_lock`) scoped to the whole chain — without it, two concurrent writers reading "the latest entry" unlocked could both build on the same `prev_hash` and corrupt the chain.

**Design tradeoff, named not hidden**: the hash uses the *application's* clock, not Postgres server time — server time is only knowable *after* insert, and the append-only design (writer role is INSERT-only, per the scoping doc's §10.7) forbids updating a row afterward to fix that up. Real timestamp signing is named as deferred v0.2 scope for regulated deployments.

**Schema** (`audit_entries`): `id`, `trace_id`, `span_id`, `parent_id` (self-referencing FK, links `INTENT`/`HELD` rows to their `COMPLETED`/`DENIED` follow-up), `timestamp`, `status`, `agent_id`, `session_id`, `server`, `tool`, `args_hash`, `args_redacted` (JSONB), `policies_fired` (JSONB), `decision` (JSONB), `latency_ms`, `tokens` (JSONB), `prev_hash`, `this_hash`, `hitl_ticket_id`/`hitl_reviewer`/`hitl_decision`/`hitl_rationale`, `tags` (JSONB array, added Phase 3 Day 14 for AML pack compliance tagging).

---

## 6. Human-in-the-Loop (HITL) Flow

`src/interpose/session/{redis_client,hitl}.py`. A real Redis-backed ticket queue: `interpose:hitl:{ticket_id}` (hash + TTL) and `interpose:hitl:pending` (set). `interpose review list/approve/deny` (CLI) reads/writes tickets directly.

**Deliberate architecture deviation from the scoping doc**, decided and documented, not silently changed: the scoping doc's Stage 7 reads as an async retry/resume flow; MCP's `tools/call` protocol has no such mechanism to hang a response on. Built instead as a **blocking (but async) wait on the same request** — the gateway holds the HTTP connection open (other requests unaffected) up to the policy's own `timeout_seconds`, rather than returning an immediate "held" response the agent would need to poll. Simpler, directly testable via one `asyncio.gather(make_call(), approve_shortly())`; the accepted tradeoff is a long-held connection, not a resumable-request protocol.

---

## 7. Control Plane (LangGraph, 5 Agents)

`src/interpose/control_plane/{graph,state,runner,bus}.py` + `agents/*.py`. Runs **asynchronously**, off the gateway's hot path — the gateway publishes one `DecisionEvent` per decision-defining audit write (DENIED/HELD/INTENT, never the COMPLETED/UPSTREAM_ERROR follow-ups) onto an in-process `EventBus`, and a background `asyncio.Task` (`run_forever`) consumes and processes them; a control-plane failure is logged and never affects what the gateway already returned to the caller.

**Real graph topology** (`build_graph`):

```
supervisor (A0, pure dispatch, no LLM)
  DENY → incident_escalator (A4) directly
  else → policy_evaluator (A1)

policy_evaluator (A1, no LLM — live session-feature query + risk score)
  HOLD → evidence_composer (A3)
  PASS + risk_score > 0.5 → anomaly_detector (A2)
  else → END

anomaly_detector (A2, optional LLM — only for a high-severity flag's plain-English description)
  severity == "high" → incident_escalator (A4)
  else → END

evidence_composer (A3, mandatory LLM — HITL reviewer narrative) → END
incident_escalator (A4, mandatory LLM — incident narrative + response classification) → END
```

**Named gap in the graph itself**: the scoping doc's 4th incident-promotion trigger ("risk score > 0.8 with a pending HITL hold") is implemented correctly in `incident_escalator`'s own logic, but is **not reachable** via the graph today — A3 has no outgoing edge back to A4.

**Agent A1 (Policy Evaluator)**: computes session features live from `audit_entries` (not the scoping doc's 15-minute materialized view — that Spark job doesn't exist). 3 of 7 documented features deliberately not computed, each with a named missing dependency. The risk-score formula is an explicit hand-weighted heuristic, documented as non-calibrated (no production traffic exists yet to calibrate against).

**Agent A2 (Anomaly Detector)**: a live agent-scoped z-score over recent call-rate windows (no population baseline exists to compare against — returns `None`, not a default, below 3 windows of history or zero variance) plus a repeated-denials rule. Cluster-deviation detection (K-means) deferred — needs a Spark training job that doesn't exist.

**Agent A4 (Incident Escalator)**: 3 of 4 promotion rules real and reachable; found and fixed a real severity-reporting bug where `should_promote`'s rule-priority order (repeated-denials checked before anomaly-severity) under-reported a co-occurring high-severity anomaly as `med` — fixed by having `compute_incident_severity` check co-occurrence independently of which rule matched first.

**Control-plane persistence** (`src/interpose/control_plane/models.py`, closed as a Phase 3 gap — previously computed and discarded): `anomaly_flags`, `incidents` (id reuses the real `Incident.incident_id` UUID), `risk_score_snapshots` — all sharing `audit.models.Base`, deliberately no FK to `audit_entries` (several tests use an unseeded placeholder `audit_id`, matching the precedent `AuditEntrySynthetic.parent_id` already set), deliberately no Spark aggregation (real control-plane volume — tens to thousands of rows — makes a direct query simpler and just as fast as pre-aggregating it).

---

## 8. MCP Servers

Three real, standalone MCP servers behind the gateway — each its own process, own Dockerfile, zero dependency on `src/interpose/` (the same shape a real third-party production MCP server would have).

| Server | Port | Tools | Real data |
|---|---|---|---|
| `examples/hello-mcp-http-echo` | 9001 | `echo`, `dangerous_tool` (denylist demo), `throttled_tool` (rate_limit demo), `hitl_tool`/`hitl_timeout_tool` (hitl_gate demos), `echo_untrusted`/`leaky_echo` (adversarial-suite demos) | None — pure demo fixture |
| `mcp-servers/ofac-sanctions` | 9002 | `check_entity(name, entity_type)`, `check_alias(name)`, `get_entity_detail(sdn_entry_id)` | **Live** U.S. Treasury OFAC SDN list — 19,169 entries + 20,159 alias rows, fetched fresh from `sanctionslistservice.ofac.treas.gov` on every start; RapidFuzz-based matching |
| `mcp-servers/transaction-graph` | 9003 | `query_transactions`, `get_account`, `neighbors` (k-hop BFS), `subgraph` (induced subgraph), `structuring_check` (BSA/CTR-threshold heuristic), `mark_investigated` (the one write tool — `disposition ∈ {cleared, escalate, monitor}`, in-memory, resets on restart) | IBM AML Kaggle dataset (CDLA-Sharing-1.0), subsampled from 31.9M raw transactions to **500,000 accounts / 3,158,483 transactions** (seed 42; all 35,230 labeled-laundering transactions retained; 100/100 sampled laundering patterns verified fully connected), queried via DuckDB directly over partitioned Parquet |

---

## 9. AML Investigation Agent (Client, Not Part of Interpose)

`agents/aml-investigator/` — deliberately a *client* of Interpose, architecturally distinct from the control plane (§7): a linear 5-node LangGraph (`discovery → enrichment → assessment(LLM) → recommendation → report(LLM)`), not a ReAct loop, and not part of the gateway process. `InvestigationClient` opens two real MCP `ClientSession`s (one per upstream server) sharing one `httpx.AsyncClient` with a consistent `Authorization: Bearer investigation-<uuid>` header across both — the mechanism that makes the AML pack's cross-server `aml-sanctions-required` policy answerable at all (§10 explains why `session_id` can't do this). Both LLM nodes (`assessment`, `report`) reuse `interpose.control_plane.llm.generate_structured` directly (a deliberate, named exception to the "MCP servers have zero `interpose` dependency" rule — this package is a client, not a server) and both have a deterministic fallback on `LLMError`. Section 9.7 targets ~40-60 tool calls per demo run.

---

## 10. AML Policy Pack

`policies/packs/aml/` — 6 of the scoping doc's 7 planned policies (P7 `cost_cap` deliberately not activated; see §4).

| Policy | Effect | What it does |
|---|---|---|
| `aml-sanctions-required` | custom / request | Blocks every `transaction-graph` write/read (except `get_account`, deliberately excluded to avoid a chicken-and-egg dependency) until a `COMPLETED` OFAC `check_entity`/`check_alias` exists for the **same agent** — correlated on `agent_id`, not `session_id` (confirmed live: two real connections through the gateway to two different upstream servers came back with two completely different `Mcp-Session-Id` values) |
| `aml-write-hitl-gate` | hitl_gate | Every `mark_investigated` write requires human approval — reviewer group `aml-analysts`, 3600s timeout |
| `aml-pii-redaction` | pii_redaction | `server: "*"`, all 3 real PII patterns |
| `aml-rate-limit-sanctions` | rate_limit | `check_entity`, 60 calls/60s |
| `aml-structuring-alert` | custom / response | Tags a high-severity incident when `structuring_check` returns `flagged=true` — **detects and tags only**, does not (cannot) block the response, the real precedent that later informed the adversarial suite's own `prompt_injection_via_tool_output` design (§14) |
| `aml-audit-tagging` | tag_only | `server: "*"`, tags every governed call `pack:aml`/`regulation:BSA` for compliance reporting |

---

## 11. Observability: Tracing + Metrics

**Tracing** (`src/interpose/observability/tracing.py`): OTel auto-instrumentation for FastAPI (root span per HTTP request), httpx (child span per upstream forward), SQLAlchemy (audit writes), plus one manual span (`policy.evaluate`) for the one gateway stage with no library to instrument. A real bug found only by looking at a live trace: every span appeared as its own disconnected one-span trace until `setup_tracing()` was split out to run *before* the FastAPI lifespan, not inside it — `FastAPIInstrumentor.instrument_app()` patches a method Starlette calls (and caches) exactly once, on the app's first ASGI event, which the lifespan startup itself is.

**Metrics** (`src/interpose/observability/metrics.py`, closed as a Phase 3/4 gap) — 5 OTel instruments matching the scoping doc's golden-signal table exactly, reusing the same OTLP pipeline as tracing rather than a separate `prometheus_client` integration:

| Metric | OTel instrument | Labels |
|---|---|---|
| `interpose_tool_calls_total` | Counter | `{server, tool, outcome}` — outcome ∈ `deny, hold_timeout, hold_denied, upstream_error, completed` |
| `interpose_tool_call_errors_total` | Counter | `{error_type}` — `upstream_unreachable, response_policy_error, policy_engine_error` |
| `interpose_tool_call_duration_seconds` | Histogram | `{server, tool}` |
| `interpose_gateway_inflight` | **UpDownCounter** (not a "gauge" — see §20 for why) | — |
| `interpose_policy_fires_total` | Counter | `{policy_name, effect_type, outcome}` |

A real OTel Collector (`otel/opentelemetry-collector-contrib:0.111.0`) + a single-replica Prometheus (`prom/prometheus:v2.55.1`) were added to the Helm chart, gated behind `otelCollector.enabled`/`prometheus.enabled` (off in production-leaning `values.yaml`, on in `values-dev.yaml` — the 3rd application of the embedded-vs-external toggle pattern). Dashboard 1 (Gateway Health) was fully rewritten around real PromQL — the only one of the 4 dashboards where the synthetic approximation was fully replaced rather than kept alongside real data, since it was always explicitly named as temporary scaffolding.

---

## 12. Analytics Pipeline (Spark)

**Dataset subsampling** (Phase 0, `interpose.analytics.subsample_aml`): real 31.9M-row IBM AML CSV → 500,000 accounts / 3,158,483 transactions in ~3.5 minutes, `local[*]`.

**Synthetic telemetry** (Phase 3 Day 15, `interpose.analytics.generate_synthetic_telemetry`): **10,004,966 rows**, 500 agents, 100 tools across 20 servers, a 4-week window with a real diurnal cycle + weekend dip, 3 incident windows, 1 coordinated-attack simulation — generated in under a minute by computing the per-hour target row count once against a 672-row bucket table and exploding directly, avoiding a join against the full 10M rows a naive weighted-sampling approach would need.

**Real technical pivot**: Spark's JDBC write to Postgres didn't work in this environment (`spark.jars.packages`'s Ivy dependency resolution came back empty with no error, despite confirmed internet access) — pivoted to the already-proven pattern (Spark writes Parquet, a plain Python `pyarrow` + `COPY` loader reads it into Postgres), ~3.5 minutes for 10M rows.

**5 aggregate tables** (`agg_telemetry_hourly`, `agg_policy_fires_daily`, `agg_hitl_daily`, `agg_aml_pack_daily`, `agg_cost_daily`) — two real cardinality/correctness bugs caught by checking actual row counts and category totals, not assuming a query that ran without error was correct (§20).

---

## 13. Kubernetes Deployment (Helm Chart)

`charts/interpose/` — **23 template files** across 8 components (root gateway resources, `postgres/`, `redis/`, `grafana/`, `otel-collector/`, `prometheus/`). Deployed to local `kind` clusters via `scripts/dev-up.sh` (idempotent — safe to re-run) in **99-110 seconds measured**, against a target of under 5 minutes.

**A real Service-selector bug**, live-cluster-only, `helm template` would never have caught it: the gateway `Service` initially matched on labels shared by *every* workload in the release (gateway, Postgres, Redis, Grafana), so `kubectl port-forward svc/gateway` nondeterministically connected to whichever pod — fixed with an `app.kubernetes.io/component` label added to every selector.

**A real ConfigMap/pod-restart bug** (Phase 3 gap-closing): setting `policies.pack=aml` and running `helm upgrade --wait` reported success while the running pod kept serving the old ConfigMap indefinitely — Kubernetes never restarts a pod just because a ConfigMap it mounts changed. Fixed with `checksum/config`/`checksum/policies`/`checksum/upstreams` pod-template annotations, hashing each ConfigMap's rendered content.

**A real Kubernetes env-var-injection bug**: Kubernetes auto-injects Docker-links-style env vars for every Service in a namespace into every pod (`<SVCNAME>_PORT=tcp://...`); the `transaction-graph` Service's own name collided exactly with that app's own `TRANSACTION_GRAPH_` pydantic-settings env prefix, silently overwriting its `port` setting with a URL and crash-looping the pod. Fixed with `enableServiceLinks: false` on all three dev-fixture Deployments.

**Embedded-vs-external toggle pattern**, applied consistently across the whole chart: `postgres.embedded`/`redis.embedded` (Phase 2), `otelCollector.enabled`/`prometheus.enabled` (Phase 3/4) — `false` in production-leaning `values.yaml` defaults (a real deployment brings its own managed service), `true` in `values-dev.yaml` (a fully self-contained `kind` install).

**4 Grafana dashboards** (`charts/interpose/files/dashboards/*.json`):

| Dashboard | Data source | Notable panels |
|---|---|---|
| 1 — Gateway Health | **Real Prometheus** (fully rewritten, Phase 4) | Tool calls/sec by outcome, latency p50/p95/p99, error rate, in-flight saturation, per-server health table |
| 2 — Policy & Governance | Synthetic Postgres + **real** control-plane tables | Policy fires/day, HITL queue depth/response time/ratio (synthetic); real anomaly-flag and incident-promotion panels (Phase 3 gap-closing) |
| 3 — AML Pack (demo) | Synthetic Postgres + **real** risk-score table | OFAC call volume, structuring alerts, `mark_investigated` outcome ratio (synthetic); real session-level risk-score distribution (Phase 3 gap-closing) |
| 4 — Cost Telemetry | Entirely synthetic | Token spend per agent/provider, projected monthly cost — the gateway has zero real LLM-cost visibility to back this with real data |

---

## 14. Adversarial Test Suite & Eval Harness

`tests/adversarial/` — all **6 required attack classes**, live-verified through a real gateway + real upstream subprocess pair per class, never mocked gateway internals:

| Attack class | Defense mechanism | Scenarios |
|---|---|---|
| `prompt_injection_via_tool_output` | Response-side custom policy **detects and tags**, honestly does not block (matches `aml-structuring-alert`'s own real precedent) | 4 |
| `data_exfiltration` | `rate_limit` denies past the window | 4 |
| `unauthorized_write` | `hitl_gate` — nobody approves, it times out and denies | 4 |
| `over_permissioned_tool_access` | `allowlist` default-denies by omission | 2 |
| `credential_leakage` | `pii_redaction` — real response content verified redacted | 3 |
| `chained_tool_privilege_escalation` | Repeated denials promote a real row in the `incidents` table, via the direct DENY→Agent A4 graph path | 3 |

**20 total generated scenarios** (seeded, `random.Random(42)`), deliberately scoped down from the scoping doc's literal ~500-1000 variants/class — that number is templated-argument-permutation volume, not meaningfully different attacks; confirmed as an explicit scope decision rather than assumed.

**Two real design mistakes, both found by running the suite live, both fixed by restructuring, not patching:**
1. Put a new allowlist demo policy in the same directory as pre-existing hitl_gate/rate_limit demo policies — broke two passing tests, because of §4's allowlist-bypasses-everything rule. Fixed by giving every attack class its own fully isolated `policy_dir` — a structural fix that makes the bug class impossible, not a one-off patch.
2. Initially assumed a response-side custom policy could "fail-closed block" a response — wrong; confirmed against `interpose.policies.custom`'s own documented design boundary and `aml-structuring-alert`'s real behavior (§10). Corrected before writing more code.

**Eval harness** (`scripts/run_eval_report.py`) closes a real, previously-unscoped gap: the scoping doc references an eval harness and an "evaluation report JSON" release deliverable, but the project's own roadmap never scheduled building one anywhere. Rather than invent a second evaluation concept, this script reuses the adversarial suite's own harness directly — same scenarios, same live-gateway execution, pointed at producing a JSON summary instead of a pytest failure. CI uploads it as a build artifact on every run.

---

## 15. CLI

Entry point: `interpose` (Typer). Commands:

| Command | Options | Purpose |
|---|---|---|
| `verify-audit` | `--since YYYY-MM-DD` | Walks the full hash chain from genesis regardless of `--since` (a filter narrows the report, never the verification scope); exit 1 on a broken chain |
| `review list` | — | Lists pending HITL tickets |
| `review approve <ticket_id>` | `--reviewer`, `--rationale` | Approves a held call |
| `review deny <ticket_id>` | `--reviewer`, `--rationale` | Denies a held call |
| `demo aml` | `--setup`, `--run`, `--account-id`, `--gateway-url` | `--setup` shells to `scripts/dev-up.sh`; `--run` shells to the real investigation agent, then verifies the resulting audit chain |

---

## 16. CI/CD (GitHub Actions)

`.github/workflows/ci.yml` — **5 jobs**, every push/PR to `main`:

| Job | What it does |
|---|---|
| `lint` | `ruff check .` |
| `helm` | `helm lint` + `helm template` (dummy `groqApiKey`) |
| `terraform` | `terraform fmt -check`, then `init -backend=false` + `validate` for both the module and `examples/minimal/` — **no AWS credentials configured at all**, so `plan`/`apply` are structurally unreachable in CI |
| `test` | Real Postgres 16 + Redis 7.4-alpine service containers, `alembic upgrade head`, `pytest --ignore=tests/adversarial` |
| `adversarial` | Same real services, `pytest tests/adversarial/ -v`, then `scripts/run_eval_report.py`, then uploads `eval_report.json` as a build artifact |

---

## 17. Test Coverage (327 Tests)

| Directory | Count |
|---|---|
| `tests/unit/policies` | 101 |
| `tests/unit/control_plane` | 69 |
| `tests/unit/agents` | 29 |
| `tests/unit/mcp_servers` | 29 |
| `tests/unit/cli` | 10 |
| `tests/unit/audit` | 12 |
| `tests/unit/observability` | 7 |
| `tests/unit/analytics` | 2 |
| `tests/unit/test_placeholder.py` | 1 |
| **Unit total** | **260** |
| `tests/integration/` | 45 |
| `tests/adversarial/` | 22 |
| **Grand total** | **327** |

No mocking of the systems under test: integration tests spin up real subprocess gateways and real upstream MCP servers on real ports (a deliberate choice — streamable-HTTP's long-lived GET stream needs a live server to exercise honestly, not an in-process ASGI test client), and query real Postgres/Redis. `pyproject.toml`'s `pythonpath` config lets tests import each standalone MCP server's own modules directly (`mcp-servers/*/src`, `agents/aml-investigator/src`) without packaging them.

**Verified twice back-to-back at multiple points in the project** (not just once) specifically to catch test-isolation bugs a single green run wouldn't surface — and it did, twice (§20).

---

## 18. `concepts/` — The Learning Artifact

37 numbered concept documents (`concepts/00` through `concepts/36`), one topic per file, written alongside the code as new tools/ideas became load-bearing — not a single retrospective writeup. Spans: CLAUDE.md conventions, MCP itself and its handshake/transports, the gateway/proxy architecture and its 3 planes, SLA/SLO framing, the AML/OFAC domain glossary, Python/uv, Docker, Kubernetes, Terraform/IaC, git branching, OSS community files, session-continuity conventions, Spark/PySpark, FastAPI, the policy engine's composition rules, fail-closed enforcement, Postgres/SQLAlchemy/Alembic, the hash-chained audit log, the CLI, Redis + the HITL hold, LangGraph fundamentals, the control-plane event bus, real-LLM narrative generation, the remaining control-plane agents, Helm, OpenTelemetry tracing, fuzzy matching, embedded analytics with DuckDB, client vs. control-plane agents, response-side policy evaluation, synthetic telemetry, persisting control-plane decisions, metrics/Prometheus, adversarial testing/evaluation, and Terraform/IRSA. Full index: `concepts/INDEX.md`.

---

## 19. Real Bugs Found and Fixed

Every one of these was found by actually running something — a live API call, a live cluster, a live trace, a repeated test run — not by code review or a passing unit test suite alone.

| # | Phase / Day | Bug | Found by | Fix |
|---|---|---|---|---|
| 1 | Phase 0 | Homebrew `autoremove` silently uninstalled `node`/`mongosh` | Manual observation | Reinstalled both |
| 2 | Phase 0 | Scoping doc claimed HI-Medium dataset ~180M rows | Actual download | Corrected to ~32M rows in project docs |
| 3 | Phase 0 | Scoping doc claimed CC-BY 4.0 license | Checked the real license file | Corrected to CDLA-Sharing-1.0 |
| 4 | Phase 0 | Scoping doc predicted ~8-12M transactions would survive subsampling | Real measured run | Actual: 3.16M |
| 5 | Phase 0 | Scoping doc claimed an account-level `is_launderer` flag exists | Inspecting raw data | Doesn't exist — labels are transaction-level only |
| 6 | Day 1 | Stray gateway subprocess from an earlier fixture teardown held port 8000 | Flaky test run | `terminate()` fallback to `kill()` on timeout |
| 7 | Day 5 | ROADMAP's Phase 1 gate wrongly claimed a LangGraph agent makes a call through Interpose | Cross-checking against the scoping doc | Corrected with an explanatory note, not a silent edit |
| 8 | Day 5 | Typer silently collapsed the CLI to a flat single-command form | First real CLI invocation | Empty `@app.callback()` |
| 9 | Day 8 | `should_promote` checked repeated-denials before anomaly-severity, under-reporting a co-occurring high-severity anomaly as `med` | Integration tests | `compute_incident_severity` checks co-occurrence independently of which rule matched first |
| 10 | Day 8 | `HITLPacket.ticket_id` needed a real Redis ticket ID, but the gateway published its `DecisionEvent` before the ticket existed | Building Agent A3 | Reordered `_handle_hold`; added `hitl_ticket_id` to `DecisionEvent` |
| 11 | Day 8 | Groq's strict JSON-schema mode requires `additionalProperties: false`; Pydantic doesn't set it by default | Real live Groq API call | Fixed centrally in `_strict_schema`, permanent regression test |
| 12 | Day 8 | `openai/gpt-oss-20b` spent its whole token budget on hidden reasoning before any JSON, on longer prompts | Real live Groq API call | `reasoning_effort="low"` |
| 13 | Day 8 | Once a real `GROQ_API_KEY` existed locally, "fallback path" tests silently started calling the real API | Noticed after adding the key | `tests/conftest.py` forces `GROQ_API_KEY=""` unconditionally for the whole test session |
| 14 | Day 9 | Gateway `Service` selector matched labels shared by *every* workload in the release — port-forward nondeterministically hit the wrong pod | Live `kind` cluster only, `helm template` never would have caught it | `app.kubernetes.io/component` label on every selector |
| 15 | Day 9 (found mid-build) | No migration Job — fresh Postgres had no schema, `/readyz` reported healthy while every audit write 500'd | Not in the original day's plan, found while building | `migrate-job.yaml` Helm hook Job |
| 16 | Day 10 | Every OTel span appeared as its own disconnected one-span trace | Real live Jaeger check | `FastAPIInstrumentor.instrument_app()` moved to run *before* the FastAPI lifespan, not inside it |
| 17 | Day 11 | RapidFuzz's default scorer is case-sensitive; SDN list is all-caps — a correctly-cased real query scored its real match ~14%, losing to unrelated candidates, with no crash | Test-caught, not obvious from code review | `rapidfuzz.utils.default_process` as the processor |
| 18 | Day 12 | DuckDB's CSV type inference treats numeric-looking IDs as INTEGER; real Parquet IDs are always strings | First real run against actual data | Explicit `CAST` to VARCHAR in both DuckDB view definitions |
| 19 | Day 12 | Upstream `mcp` package shipped a breaking `2.0.0` release between Day 11 and Day 12, renaming/removing `mcp.server.fastmcp`; Dockerfiles had only a lower-bound pin | Fresh Docker rebuild | Pinned exact `mcp[cli]==1.28.1` in both standalone Dockerfiles |
| 20 | Day 13 | Seed generator used a fixed `OFFSET (seed % 97)` — worked by accident against the real 35,230-row dataset, returned nothing against a 2-3-row test fixture | Own test suite | Bounded the offset to the real candidate count |
| 21 | Day 14 | `aml-sanctions-required` initially correlated on `session_id` | Live test: two real gateway connections to two different upstream servers, compared session IDs directly | Redesigned around `agent_id` (consistent `Authorization` header across both connections) |
| 22 | Day 14 | Buffered response-parsing path assumed bare JSON | First live call failed with a JSON decode error | FastMCP responds SSE-framed (`text/event-stream`) for every `tools/call` — explicit encode/decode helpers |
| 23 | Day 14 | `aml-sanctions-required`'s `tools: ["*"]` scope would gate `get_account` too, but `get_account` is the only source of the entity name `check_entity` needs — an unsatisfiable chicken-and-egg | Design review before shipping | Excluded `get_account` from scope |
| 24 | Day 14 | `InvestigationClient`'s error handling only checked `result.isError`; a gateway policy DENY is a JSON-RPC-envelope-level `McpError`, not a tool-result error | Integration test — shipped Day 13, invisible until a real policy pack existed to produce a DENY | Fixed error handling to catch `McpError` |
| 25 | Day 15 | `agg_cost_daily` grouped by `{day, agent_id, tool, provider}` produced 918,819 rows, most combinations near-empty | Checking actual row counts, not assuming a successful query was correct | Dropped `tool` from the grouping |
| 26 | Day 15 | `agg_aml_pack_daily`'s pending-count column double-counted with the approved column | Checking category totals against the whole | Renamed and required `hitl_decision IS NULL`; documented as a synthetic-generator-only artifact |
| 27 | Gap-closing pt.1 | Kubernetes auto-injects Docker-links env vars per Service in a namespace; `transaction-graph`'s Service name collided exactly with its own `TRANSACTION_GRAPH_` settings prefix, overwriting its port with a URL | Watching the pod crash-loop live | `enableServiceLinks: false` on all dev-fixture Deployments |
| 28 | Gap-closing pt.1 | Chart's policy ConfigMap only ever globbed the demo pack — the real AML pack was never wired into the chart at all | Trying to prove the AML pack was enforced in-cluster | `policies.pack` values.yaml toggle + checked-in copy + a chart-policy-sync test |
| 29 | Gap-closing pt.1 | `helm upgrade --wait` reported success while the running pod kept serving the *old* ConfigMap | Live-verifying fix #28 | `checksum/*` pod-template annotations |
| 30 | Gap-closing pt.2 | `clean_state` test fixture only truncated `audit_entries`, not the 3 new control-plane tables — invisible until the full suite ran twice in a row | Deliberately running the suite twice, not once | Truncate all 3 tables in the same fixture |
| 31 | Gap-closing pt.2 | Some test scenarios run the graph twice against the same input (once via `astream`, once via `ainvoke`) — 2 matching rows land, not 1 | Same double-run discipline | Order the read-back query, assert on the most recent row |
| 32 | Gap-closing pt.3 | OTel SDK's *default* histogram bucket boundaries are millisecond-tuned; a seconds-denominated histogram put nearly all real ~30ms latencies in the first bucket, reporting a **p95 of 4.75 seconds** for calls that took ~25ms | Only computing a real `histogram_quantile()` against real scraped Prometheus data — unit tests, `ruff`, and the raw `/metrics` output all looked fine | `explicit_bucket_boundaries_advisory` set to the real seconds-scale semantic-convention default |
| 33 | Day 16 | Putting a new allowlist demo policy alongside existing hitl_gate/rate_limit demo policies broke 2 passing tests, via the allowlist-bypasses-everything rule (§4) | Running the adversarial suite | Fully isolated `policy_dir` per attack class |
| 34 | Day 16 | Assumed a response-side custom policy could fail-closed block a response | Re-reading `custom.py`'s own docstring + `aml-structuring-alert`'s real behavior | Corrected before writing more code — detect-and-tag only |
| 35 | Day 17 | `aws_eks_cluster`'s `encryption_config` written with a flat `provider_key_arn` attribute — wrong schema | `terraform validate`, zero AWS involved | Nested `provider { key_arn = ... }` block |

---

## 20. Key Engineering Decisions

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Governance mechanism | A transparent network proxy | A client-side library | A library only helps agents that choose to import it; a proxy governs any MCP client regardless of framework — one governance point for an org with many independent agent teams |
| Protocol compatibility | Fully transparent (no custom MCP fields, no server-side changes required) | A fork/extension of MCP | Keeps Interpose usable with any MCP server or client that already exists |
| HITL request handling | Block (async) on the same request, up to the policy's timeout | The scoping doc's literal "immediate held response + async resume" | MCP `tools/call` has no resume mechanism to hang a response on; blocking is simpler, directly testable, and the tradeoff (a long-held connection) is accepted explicitly |
| Audit timestamp source | Application clock | Postgres server time | Server time is only known *after* insert; the append-only audit design forbids updating a row afterward to fix it — real timestamp signing named as deferred v0.2 |
| Concurrent audit writes | Postgres advisory lock scoped to the whole chain | Optimistic concurrency / no lock | Two unlocked concurrent writers could both build on the same `prev_hash` and corrupt the chain |
| Custom policy extensibility | A small, named-function registry (`interpose.policies.custom`) | Arbitrary code embedded in policy YAML | A policy pack is data a deployer can drop into `config/policies` at runtime — data that can execute arbitrary code is a code-injection vector, not a policy |
| Response-side custom policies | Detect + tag only, cannot deny an already-completed call | A response-side "block" capability | A stated architectural boundary — the response already happened; the honest capability is flagging it, not pretending to intercept it after the fact |
| Cross-server correlation for AML sanctions-check | `agent_id` (consistent `Authorization` header) | `session_id` (MCP transport's `Mcp-Session-Id`) | Confirmed live: `session_id` is assigned independently per upstream server's own handshake — two connections to two servers get two unrelated session IDs |
| AML `mark_investigated` gating | Unconditional `hitl_gate` on the one write tool | A conditional gate reading the structuring-alert flag | The unconditional gate already covers every case the conditional one would; building a second enforcement path for something already fully covered is dead code, not a missing feature |
| LLM provider | Groq | Anthropic Claude (the scoping doc's eventual production default), OpenAI | Genuine free tier for a learning project's dev-time cost, explicitly provider-swappable by design |
| Structured LLM output | Real strict-schema/function-calling structured output | Prompt-and-hope JSON parsing | Deterministic validation against a real schema, not regex-scraping model prose |
| Multi-agent orchestration (control plane) | LangGraph, conditional edges | A linear prompt chain, an open-ended ReAct loop | The control plane's real shape (dispatch → enrich → maybe escalate, with real routing conditions) is what a stateful graph is for |
| Investigation agent shape | A linear 5-node graph | An open-ended ReAct tool-selection loop | Deterministic, auditable, cheaper — matches how the client actually needs to reason (gather evidence → assess → recommend), not open-ended exploration |
| Metrics pipeline | Reuse the existing OTel tracing pipeline (OTLP → Collector → Prometheus) | A separate `prometheus_client` + hand-rolled `/metrics` endpoint | One dependency set, one mental model, one Collector receiving both signals — no new packages needed |
| `interpose_gateway_inflight` instrument type | `UpDownCounter` | An OTel asynchronous "gauge" | A gauge is callback-based (report the current value on request); this value is a running increment/decrement total, which is exactly what an UpDownCounter is for — the Collector still renders it as a Prometheus gauge on export either way |
| Kubernetes chart resources | First-party, hand-rolled Postgres/Redis Deployments | The Bitnami Postgres/Redis Helm sub-charts | An external chart-repo dependency buys nothing for a dev-only convenience toggle a dozen lines of YAML already covers plainly |
| Terraform module resources | Hand-rolled AWS resources (VPC, EKS, RDS, etc.) | `terraform-aws-modules/vpc`, `.../eks` | Same reasoning as the Helm chart — the module's whole purpose is demonstrating real, first-principles understanding, not delegating it to someone else's abstraction |
| Embedded vs. external infra toggle | A `*.enabled`/`*.embedded` boolean per service, off by default in production values, on in dev values | One fixed deployment shape | Applied consistently 3× (Postgres/Redis; OTel Collector/Prometheus; Terraform's ElastiCache/custom KMS) — a real production deploy brings its own managed service, a dev install is fully self-contained |
| Terraform secrets | `random_password` → AWS Secrets Manager, never a plain variable or raw output | A `variable` with a default, or a `sensitive` output | Real secret material never appears in a `.tfvars` file or `terraform output`; only Secrets Manager ARNs are exposed |
| IRSA role scope | Narrow, per-need (Secrets Manager read for exactly 2 secrets, S3 read/write for exactly 1 bucket) | The node group's own broad instance-profile permissions | A pod's AWS identity should reflect what that pod actually needs, not what every pod on that node happens to inherit |
| Adversarial-suite policy isolation | One fully isolated `policy_dir` per attack class | One shared adversarial policy pack | The allowlist-bypasses-everything rule (§4) makes any shared pack containing both an allowlist and a hitl_gate/rate_limit policy silently break the latter — isolation makes the bug class structurally impossible |
| Adversarial fixture volume | 2-4 real, seeded variants per class (20 total) | The scoping doc's literal ~500-1000 per class | That number is templated-argument-permutation volume, not meaningfully different attacks; CI cost of a live gateway round trip per near-duplicate variant isn't worth the marginal signal |
| Eval harness | Reuse the adversarial suite's own harness, pointed at JSON output | A separate, purpose-built evaluation framework | The harness already *is* an evaluation harness by the scoping doc's own definition (run a scripted scenario against the real system, check pass/fail) — building a second one would duplicate the exact same mechanism |
| Test isolation verification | Explicitly run the full suite twice back-to-back at multiple points | Trust a single green run | Found two real cross-run isolation bugs this way that a single run never would have surfaced |
| Terraform live-apply scope | Build + statically validate only this phase; live `apply`/`destroy` deferred to a separate, explicit decision | Apply immediately as part of "build the module" | Real AWS cost begins the moment `apply` succeeds — that's a cost-aware decision distinct from writing correct infrastructure code |

---

## 21. Success Metrics vs. Target (Scoping Doc §4.6)

**Category A — Code and functionality (CI-verifiable):**

| Metric | Target | Actual |
|---|---|---|
| Unit tests | ≥100 | **260** |
| Integration tests | ≥20 | **45** |
| Attack classes caught | ≥6 documented, live-verified | **6/6, live** |
| Policy types supported | ≥5 | **8** (allowlist, denylist, rate_limit, pii_redaction, hitl_gate, custom, tag_only, cost_cap) |
| Documented policies | 100% via YAML | **Met** — 24 real policy files, zero code-embedded policy logic |
| Helm deploy time | <5 min | **99-110s measured** |
| Terraform apply time | <20 min | **Not yet measured** — no live apply performed |
| CI pipeline green | 100% on `main` | **Met** — 5 jobs, all green |

**Category D — Resume-gap closure:**

| Gap | Target | Actual |
|---|---|---|
| LangGraph / multi-agent | Closed | **5 control-plane agents (A0-A4) + a 6th, architecturally distinct client-side agent** |
| Kubernetes | Working knowledge | Helm chart (23 templates) + a running, live-verified deployment |
| Terraform / IaC | Working knowledge | AWS EKS module built + `terraform validate`-clean; **not yet live-tested against real AWS** |
| Spark / distributed data | Working knowledge | 10M+ records processed (synthetic telemetry) + a real 31.9M→3.16M subsampling job |
| MCP protocol depth | Advanced | Full gateway implementation across 3 real, standalone MCP servers |
| Multi-agent evaluation | Working knowledge | Eval harness in CI, real JSON report artifact every run |

---

## 22. Known Limitations & Future Work

| Item | Type | Notes |
|---|---|---|
| No live `terraform apply`/`destroy` against real AWS | Limitation, deliberate | Module is statically validated only (`fmt`, `validate`, both locally and in CI); real cost begins the moment `apply` succeeds, deferred to a separate explicit decision |
| No control-plane persistence in-cluster verification | Limitation, deliberate | Local Postgres/Redis verification is thorough (twice back-to-back); in-cluster live check was attempted then explicitly abandoned after establishing the observed "hangs" were self-inflicted testing artifacts, not real bugs |
| `interpose demo aml --run`'s audit-verification reads local `DATABASE_URL` | Limitation, named not silent | Reports "no audit entries found" when pointed at a remote/in-cluster gateway — the investigation itself is correct, only the CLI's own verification step looks at the wrong database |
| The 4th incident-promotion rule (risk >0.8 + pending HITL) isn't reachable | Limitation, named not silent | Correct in `incident_escalator`'s logic, but Agent A3 has no graph edge onward to Agent A4 |
| No in-cluster trace backend | Limitation, named not silent | OTel Collector's traces pipeline has nowhere real to send in `kind`; Jaeger only exists for bare local dev |
| Dashboard 4 (Cost Telemetry) is entirely synthetic | Limitation, named not silent | The gateway has zero real LLM-cost visibility to back it with real data |
| No Postgres append-only role enforcement | Limitation, deferred | The hash chain proves tampering is *detectable*; nothing today prevents an `UPDATE` at the database-role level per the scoping doc's own §10.7 |
| `cost_cap` policy effect | Not implemented | Schema-only stub; raises `NotImplementedError` unconditionally — the gateway has no LLM-cost visibility to enforce it against |
| Spark-on-Kubernetes (Spark Operator, `SparkApplication` CRDs) | Not built, deliberately cut | Already implicitly out of scope once Day 15 shipped Spark as a manual `local[*]` job instead |
| No cluster autoscaler / Karpenter in the Terraform module | Not built | Node group has static min/max bounds; nothing watches scheduling pressure and adjusts them |
| No Web UI for HITL/audit browsing/policy authoring | Not built, MVP-excluded | Named non-goal (N-adjacent) |
| No multi-region / multi-tenant architecture | Not built | v0.2 scope |
| No additional policy packs (HIPAA/GDPR) | Not built | v0.2 scope, stretch-only |
| No ML-based anomaly detection (LSTM, embedding clustering) | Not built, deliberate | A statistical z-score baseline is sufficient for MVP; explicitly declined as scope creep |
| No SAR fine-tuning / beneficial-owner discovery / case management | Not built | N1 — the AML pack is illustrative on public synthetic data, explicitly not a real compliance product |
| No LLM-provider-agnostic framework support beyond LangGraph | Not built | N10 — LlamaIndex/AutoGen/CrewAI adapters are post-MVP |
| Two blog posts | Not started | Days 18-19, meant to stay in the owner's own voice |
| Demo video | Not started | Day 19-20 |
| v0.1.0 tag / GitHub Pages chart publishing / GHCR images | Not done | Day 20 |
| Kaggle API token rotation | Loose end, flagged repeatedly, never confirmed done | Opened Phase 0, referenced through Day 14, then silently drops out of the session log |

---

## 23. Explicit Non-Goals (Scoping Doc §4.5, All Honored)

N1: not a full AML product (no SAR fine-tuning, case management, or beneficial-owner discovery beyond what MCP exposes). N2: not a general-purpose API gateway (MCP-first, no Kong/Envoy ambitions). N3: not a SIEM (produces telemetry/audit logs; downstream integration is a customer concern). N4: not a marketplace (no registry/discovery/ratings UI). N5: not a fine-tuning project (LoRA/QLoRA/PEFT explicitly out of scope for this project specifically). N6: not built for consumer AI apps (enterprise/regulated positioning only). N7: not a research paper (engineering + blog posts are the artifact). N8: not a hosted SaaS (open-source, self-hosted only). N9: not integrating commercial LLM eval platforms (LangSmith/Braintrust/Arize — v0.2+). N10: not broad agent-framework support (LangGraph flagship only for MVP).
