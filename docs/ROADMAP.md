# Roadmap (learning-paced)

The full day-by-day plan lives in `INTERPOSE_SCOPING.md` Section 14 — it was written for a
solo builder already fluent in this stack, moving at speed. This doc adapts the same
sequence and the same end-of-phase gates for someone learning the stack *while* building it.
Concretely: **same order, same milestones, no fixed days** — a "day" in Section 14 might take
us a session or three once a new concept needs explaining first. Target is still ~30 days,
flexible by about a week, per project decision on 2026-07-20.

Every phase below ends with the same gate condition Section 14 defines, and only advances once
that gate is actually met — not once time is up. That discipline (real gates, not calendar
pressure) is itself one of the things worth being able to talk about later.

## Phase 0 — Prep

**Goal (unchanged from scoping doc Section 14.4):** repo exists with a working CI skeleton, a
local Kubernetes cluster (`kind`) provisions in one command, the IBM AML dataset is downloaded
and subsampled, and a trivial MCP server runs locally.

- [x] Repo initialized, directory structure scaffolded (`src/interpose/`, `mcp-servers/`,
      `agents/`, `charts/`, `terraform/`, `policies/`, `tests/`).
- [x] `CLAUDE.md` and `concepts/` established as working conventions.
- [x] Local dev environment: Python 3.12 via `uv`, Docker, `kubectl`, `helm`, `terraform`.
- [x] `kind` installed; a test cluster provisions and tears down successfully.
- [x] IBM AML dataset downloaded (HI-Medium: 31.9M transaction rows, ~2.8GB) and subsampled to 500K accounts / 3.16M transactions via PySpark (seed 42; see `data/README.md`).
- [x] OFAC sanctions list downloaded and parsed (19,169 entries, `~/.interpose/data/ofac-sdn/sdn.csv`).
- [x] MCP Python SDK explored; a trivial "echo" MCP server built and run locally (`examples/hello-mcp-echo/`).
- [x] GitHub Actions CI skeleton (lint + test jobs, `.github/workflows/ci.yml`).

**Gate:** met — all boxes above checked. Phase 0 complete.

## Phase 1 — Foundation

**Goal (Section 14.5):** the gateway proxies real MCP traffic between a real client and a real
server; the policy engine evaluates each call; a hash-chained audit entry lands in Postgres.

Covers: FastAPI gateway request lifecycle, the policy engine (allowlist/denylist/rate-limit to
start, then PII redaction + HITL stubs), Postgres audit schema and hash chaining, an
integration test suite (docker-compose: Postgres + gateway + a mock upstream server -- Redis
deliberately deferred to Phase 2 Day 6, see Day 5's note below for why).

- [x] Day 1 — Gateway request lifecycle scaffold: FastAPI app (`src/interpose/gateway/`),
      Stages 1-3 (ingress, parse via MCP SDK, ConfigMap-stand-in route resolution) plus a naive
      streaming forward (Stages 7-9), no policy or audit yet. Verified with a real MCP client
      round trip (`initialize` / `list_tools` / `call_tool`) through the gateway to a real
      streamable-HTTP upstream server, both as live subprocesses
      (`tests/integration/test_gateway_naive_forward.py`).
- [x] Day 2 — Policy engine skeleton: Pydantic policy models (`interpose.policies.schema`),
      YAML loading/validation (`interpose.policies.loader`), three effect types (allowlist,
      denylist, rate_limit), in-memory `PolicySet`/`PolicyEngine` compilation with caching
      (`interpose.policies.policyset`). 40 unit tests passing (target was 20+).
- [x] Day 3 — Wired the policy engine into the gateway: Stages 4-5 evaluate every
      `tools/call` request; `PASS` forwards to upstream, `DENY` returns a structured
      JSON-RPC error (fail-closed on any policy-engine exception). All 5 policy types now
      parse (`pii_redaction`/`hitl_gate` added as schema stubs that raise `NotImplementedError`
      if actually evaluated, rather than silently passing through). Verified live: a real
      MCP client gets a denylisted tool call rejected with a structured error and an
      unaffected tool call still passes (`tests/integration/test_gateway_policy.py`).
      49 policy unit tests passing; 54 total tests green.
- [x] Day 4 — Postgres + audit log: schema per Section 6.7 as SQLAlchemy models
      (`interpose.audit.models`), Alembic migration applied against a real local
      Postgres (`docker-compose.yaml`, port 5433 to avoid a pre-existing unrelated
      Postgres install on this machine). Hash chain implementation
      (`interpose.audit.chain`) with 12 unit tests, including tamper detection. Stage 6
      (pre-forward INTENT write) and Stage 8 (COMPLETED/UPSTREAM_ERROR write, linked via
      `parent_id`) wired into the gateway (`interpose.audit.store.AuditStore`, advisory-
      lock-serialized writes). CI updated with a Postgres service so the pipeline stays
      green. Verified live: a real call produces two linked, hash-chain-verifying rows;
      a denied call produces one; a tampered row is caught
      (`tests/integration/test_gateway_audit.py`). 69 total tests green.
- [x] Day 5 — Buffer + integration polish: closed the "5+ end-to-end tests" checklist
      (happy path, deny path, rate-limit path — new — malformed request — new — and
      unknown server, 76 tests total green) and built `interpose verify-audit`
      (`src/interpose/cli/`, Typer-based), tested against a real Postgres including a
      genuine tamper-and-detect run through the CLI itself, not just `chain.py` in
      isolation. Deliberately **not** done today, with reasons: (1) Redis joining
      `docker-compose.yaml` — nothing consumes it yet (rate limiting is still the
      in-memory stand-in from Day 2), so it'd be unused infrastructure until Day 6's
      HITL work actually needs it; (2) containerizing the gateway and mock upstream
      via Docker for a fuller docker-compose stack — deferred to Phase 2 (Day 9,
      Helm chart + `kind`), which is where a container image becomes load-bearing
      anyway rather than a second, separate container-build exercise today.

**Gate:** met — real MCP traffic proxies through Interpose; policy fires (allow, deny, and
rate-limit paths all verified live); a hash-chained audit entry lands in Postgres and
verifies, including via `interpose verify-audit`. Phase 1 complete.

*(Corrected from the original wording, which said "a LangGraph agent makes a tool call" --
LangGraph isn't introduced until Phase 2's control-plane work per scoping doc Section 14.6.
That looks like an artifact from this roadmap's original Day-1 adaptation of Section 14, not
a deliberate requirement; the actual Section 14.5 EOW1 gate never mentions LangGraph.)

## Phase 2 — Governance

**Goal (Section 14.6):** the human-in-the-loop (HITL) approval flow works end-to-end; the
LangGraph control-plane agents are running; the full stack deploys to a local `kind` cluster
via Helm.

Covers: Redis-backed HITL ticket queue, `interpose review` CLI, the 5-agent control plane
(Supervisor, Policy Evaluator, Anomaly Detector, Evidence Composer, Incident Escalator), Helm
chart + `scripts/dev-up.sh`, first distributed trace visible in Jaeger.

- [x] Day 6 — HITL flow: Redis joins `docker-compose.yaml` (port 6379); ticket queue
      (`interpose.session.hitl`, hash + pending-set, TTL-based expiry). `hitl_gate`
      evaluates for real now (`Outcome.HOLD`, carrying `reviewer_group`/`timeout_seconds`)
      instead of raising `NotImplementedError`. Gateway blocks (async, non-blocking for
      other requests) on the held call pending a decision -- a deliberate MVP choice
      over the scoping doc's literal "immediate held response" wording, since MCP's
      synchronous `tools/call` has no built-in retry/resume mechanism (see concept 21).
      `interpose review list/approve/deny` implemented. Full HITL cycle (approve, deny,
      timeout) verified live against real Postgres + Redis
      (`tests/integration/test_gateway_hitl.py`), each producing a linked, hash-chained
      audit trail (`HELD` → `COMPLETED`/`DENIED`) with `hitl_reviewer`/`hitl_decision`/
      `hitl_rationale` populated -- schema columns that existed since Day 4, unused
      until now. Session-state hash (`interpose:session:{agent_id}`) deliberately not
      built -- nothing reads/writes a risk score yet (Day 8's anomaly detector will).
      81 total tests green.
- [x] Day 7 — LangGraph control-plane skeleton: typed state models per Section 7.4
      (`interpose.control_plane.state` -- `DecisionEvent`, `EnrichedDecision`,
      `InterposeState`, and the still-unused-until-Day-8 `AnomalyFlag`/`HITLPacket`/
      `Incident`). In-process pub/sub (`interpose.control_plane.bus.EventBus`, the
      documented seam from Section 6.17) decouples control-plane processing from the
      gateway's hot path. Supervisor (A0) implements Section 7.6's routing rule as two
      sequential conditional hops (a deliberate prose-over-diagram reading, see concept
      22); 20+ unit-test matrix. Policy Evaluator (A1) computes real session features
      live from the audit log (calls/minute, unique tools, HITL/denial counts -- 3 of
      Section 7.7's listed features deliberately not computed, each missing a named
      dependency) and writes a heuristic risk score into the previously-deferred
      `interpose:session:{session_id}` Redis hash -- its first real reader/writer.
      Agents A2/A3/A4 are placeholder stub terminal nodes (real routing to them, no
      real behavior yet -- Day 8). Verified live: a real gateway call reaches the
      control plane and A1's output lands in Redis
      (`tests/integration/test_gateway_control_plane.py`); graph-level routing and
      enrichment verified directly against real Postgres for PASS/HOLD/DENY/elevated-
      risk paths (`tests/integration/test_control_plane_graph.py`). 120 total tests
      green.
- [x] Day 8 — Remaining control-plane agents + first real LLM integration. Provider:
      Groq (free tier), via a provider-abstracted `interpose.control_plane.llm`
      wrapper -- Claude remains the documented eventual default (Section 6.4), Groq is
      an anticipated swap-in used now for cost reasons. Real structured outputs
      (`json_schema` + `strict: true`), not prompt-and-hope JSON. Agent A2 (Anomaly
      Detector): live agent-scoped z-score (no trained baseline exists) + a
      repeated-denials rule; cluster-deviation (needs Spark-trained K-means) deferred.
      Agent A3 (Evidence Composer): real evidence assembly, "prior HITL decisions" as
      a same-agent+same-tool proxy for the doc's "similar patterns." Agent A4
      (Incident Escalator): 3 of 4 promotion rules real; extended Day 7's graph with a
      new A2→A4 routing hop for high-severity anomalies (the 4th rule, via A3, still
      isn't reachable -- named gap, see concept 25). Two real bugs found only by a
      live Groq smoke test (Groq's strict mode needs `additionalProperties: false`;
      `gpt-oss` reasoning tokens can exhaust the budget before any output) -- both
      fixed and covered by permanent regression tests. Added `tests/conftest.py` so
      the automated suite never depends on a developer's local API key. 154 total
      tests green.

**Gate:** full stack deploys to `kind` via Helm; a HITL cycle completes end-to-end with a
manual approval; hash chain verifies; control-plane agents produce enriched decision events.

## Phase 3 — AML Pack

**Goal (Section 14.7):** the demo comes alive — the AML investigation agent runs a full
investigation through Interpose, including a HITL hold/resume, and Spark aggregates the
resulting audit data into dashboards.

Covers: OFAC sanctions MCP server, transaction-graph MCP server (DuckDB over the subsampled AML
data), the LangGraph investigation agent, the 7-policy AML pack, the Spark telemetry/aggregation
job, populated Grafana dashboards.

**Gate:** AML demo runs end-to-end (agent → 40+ tool calls → HITL hold → resume →
investigation report); Spark job aggregates 10M synthetic records; audit verification passes.

## Phase 4 — Proof & Polish

**Goal (Section 14.8):** the project is defensible, deployable outside `kind`, and public.

Covers: the adversarial test suite (6+ attack classes), the Terraform module deploying to real
AWS EKS, two blog posts (architecture/threat-model, and the AML case study), an edited demo
video, the v0.1.0 tag and release.

**Gate:** v0.1.0 shipped; both blog posts live; demo video public; Terraform module tested
against real EKS.

## Phase 5 — Outreach

**Goal (Section 14.9):** get in front of the three audiences the project targets (see the
scoping doc Section 3): the MCP/Anthropic community, enterprise AI-platform hiring teams, and
fintech infra teams. This phase is about people, not code — LinkedIn, targeted messages,
community posts, and folding the project into active job applications.

## What's deliberately different from Section 14 here

- No fixed "Day N" labels — phases advance on their gate, not the calendar.
- A concept explainer in `concepts/` is expected to land *before or alongside* the code that
  needed it, not after.
- End-of-phase retrospectives still happen (`docs/project/retrospectives/`), same as Section
  14.11 — useful discipline regardless of pace.
