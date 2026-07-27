# Interpose

An open-source audit and policy gateway for [MCP](https://modelcontextprotocol.io) (Model
Context Protocol) — it sits between AI agents and the MCP tool servers they call, enforcing
policy (allow/deny/redact/require-approval), and writing a tamper-evident audit trail of every
tool call. A demo AML (anti-money-laundering) policy pack, built on public synthetic data,
shows the whole system working end-to-end.

**Status:** early build, learning-in-public. See `docs/ROADMAP.md` for where things stand.

## Why this exists

Full context and rationale live in `docs/INTERPOSE_SCOPING.md`. Short version: AI agents are
increasingly given the ability to call real-world tools (send money, query databases, file
tickets). MCP standardizes *how* agents call those tools, but says nothing about *whether a
given call should be allowed*, *who approved it*, or *what happened*, after the fact. Interpose
is a transparent proxy that adds that governance layer without requiring agents or tool servers
to change.

## Quickstart

Two ways to run it. Both use `examples/hello-mcp-http-echo` as the demo upstream MCP
server until Phase 3's real OFAC/transaction-graph servers land.

**Bare, on your host** (fastest loop for iterating on code):

```sh
uv sync --all-extras --dev
cp .env.example .env                      # matches docker-compose.yaml's ports
docker compose up -d                      # postgres:5433, redis:6379
uv run alembic upgrade head
uv run python -m interpose.gateway &      # gateway on :8000
uv run python examples/hello-mcp-http-echo/server.py &   # demo upstream on :9001
```

Then drive it with a real MCP client, or inspect what it recorded:

```sh
uv run interpose verify-audit             # walks the hash chain, reports any tampering
uv run interpose review list              # pending HITL tickets, if any policy holds a call
```

**Full stack in Kubernetes (kind)** (closer to how it actually deploys):

```sh
scripts/dev-up.sh     # cluster, images, the echo-server fixture, and the Helm release
                       # -- gateway on :8000, Grafana on :3000, ~2-3 min end to end
scripts/dev-down.sh   # tears it all back down, no residual state
```

See `charts/interpose/README.md` for what the chart deploys and what's still a named
gap, and `dev/mcp-servers/README.md` for why the echo server isn't part of the chart.

## Repo layout

```
src/interpose/        # the gateway service (proxy, policy engine, audit store, control-plane agents)
mcp-servers/          # demo MCP servers used by the AML walkthrough
dev/mcp-servers/       # dev-only MCP server fixtures for the kind deployment (not the chart)
agents/                # demo LangGraph investigation agent
policies/packs/aml/    # example policy pack
charts/, terraform/    # deployment (Kubernetes via Helm, AWS via Terraform)
tests/                 # unit / integration / adversarial test suites
docs/                  # scoping doc, architecture notes, roadmap, retrospectives
concepts/              # plain-language explainers for every concept this project touches
```

## Learning as I go

I'm building this to learn, not just to ship it. `concepts/` has one short Markdown file per
concept encountered along the way (MCP, audit logging, Kubernetes, LangGraph, Terraform, Spark,
the AML domain, etc.) — written for my own future reference and for anyone else following
along. Start at `concepts/INDEX.md`.
