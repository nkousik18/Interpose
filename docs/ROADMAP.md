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
- [x] IBM AML dataset downloaded (HI-Medium: 31.9M transaction rows, ~2.8GB). Subsampling to ~500K accounts is still pending (needs Spark/PySpark set up first).
- [x] OFAC sanctions list downloaded and parsed (19,169 entries, `~/.interpose/data/ofac-sdn/sdn.csv`).
- [x] MCP Python SDK explored; a trivial "echo" MCP server built and run locally (`examples/hello-mcp-echo/`).
- [x] GitHub Actions CI skeleton (lint + test jobs, `.github/workflows/ci.yml`).

**Gate:** all boxes above checked except AML subsampling — remaining Phase 0 work.

## Phase 1 — Foundation

**Goal (Section 14.5):** the gateway proxies real MCP traffic between a real client and a real
server; the policy engine evaluates each call; a hash-chained audit entry lands in Postgres.

Covers: FastAPI gateway request lifecycle, the policy engine (allowlist/denylist/rate-limit to
start, then PII redaction + HITL stubs), Postgres audit schema and hash chaining, an
integration test suite (docker-compose: Postgres + Redis + gateway + a mock upstream server).

**Gate:** a LangGraph agent makes a tool call through Interpose to a real MCP server; policy
fires; a hash-chained audit entry is written and verifiable.

## Phase 2 — Governance

**Goal (Section 14.6):** the human-in-the-loop (HITL) approval flow works end-to-end; the
LangGraph control-plane agents are running; the full stack deploys to a local `kind` cluster
via Helm.

Covers: Redis-backed HITL ticket queue, `interpose review` CLI, the 5-agent control plane
(Supervisor, Policy Evaluator, Anomaly Detector, Evidence Composer, Incident Escalator), Helm
chart + `scripts/dev-up.sh`, first distributed trace visible in Jaeger.

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
