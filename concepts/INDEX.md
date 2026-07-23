# Concepts index

Plain-language explainers, one concept per file, added as the Interpose project introduces new
ideas. See the root `CLAUDE.md` for the rules these follow. Numbered roughly in the order each
concept was introduced.

| # | File | What it covers |
|---|------|-----------------|
| 00 | [claude-md-files.md](00-claude-md-files.md) | What a `CLAUDE.md` file is and why this repo has one |
| 01 | [what-is-mcp.md](01-what-is-mcp.md) | The Model Context Protocol: tools, servers, clients |
| 02 | [interpose-gateway-overview.md](02-interpose-gateway-overview.md) | What Interpose is, why it's a proxy, the three "planes" |
| 03 | [sla-slo-latency-budgets.md](03-sla-slo-latency-budgets.md) | SLA vs SLO vs SLI, and why latency targets are stated as percentiles |
| 04 | [aml-ofac-glossary.md](04-aml-ofac-glossary.md) | AML/KYC/OFAC/SAR/structuring/HITL vocabulary for the demo domain |
| 05 | [python-envs-and-uv.md](05-python-envs-and-uv.md) | Python version/dependency management, why `uv`, and a Homebrew autoremove lesson |
| 06 | [containers-and-docker.md](06-containers-and-docker.md) | What a container is, what Docker actually does, why Interpose needs it |
| 07 | [what-is-kubernetes.md](07-what-is-kubernetes.md) | What Kubernetes orchestrates, and how kubectl/kind fit together |
| 08 | [terraform-and-iac.md](08-terraform-and-iac.md) | Infrastructure as Code, what Terraform's job is here vs. Helm |
| 09 | [mcp-handshake-and-transports.md](09-mcp-handshake-and-transports.md) | stdio vs. HTTP transports, and the initialize/list_tools/call_tool handshake, from a real run |
| 10 | [open-data-licensing.md](10-open-data-licensing.md) | Public domain vs. CC-BY vs. CDLA-Sharing, and why we had to correct the scoping doc |
| 11 | [git-branching-and-github-flow.md](11-git-branching-and-github-flow.md) | Trunk-based vs. GitHub Flow vs. GitFlow, why we chose GitHub Flow, what branch protection does |
| 12 | [oss-community-health-files.md](12-oss-community-health-files.md) | CONTRIBUTING/CODE_OF_CONDUCT/SECURITY/CHANGELOG/templates, and what CI actually enforces |
| 13 | [session-continuity-and-progress-logs.md](13-session-continuity-and-progress-logs.md) | Why `docs/project/SESSION_LOG.md` exists, how it differs from CLAUDE.md/ROADMAP/CHANGELOG, and ADRs as a related pattern |
| 14 | [spark-and-pyspark.md](14-spark-and-pyspark.md) | What Spark/PySpark are, why a distributed engine for a laptop-sized job, the JVM/JAVA_HOME dependency, `local[*]` vs. a real cluster |
| 15 | [fastapi-and-the-naive-proxy.md](15-fastapi-and-the-naive-proxy.md) | What FastAPI is, the gateway's first (policy-free) proxy, why responses must stream not buffer, ConfigMap-driven routing before there's a ConfigMap |
| 16 | [policy-engine-composition.md](16-policy-engine-composition.md) | Declarative policy DSL, Pydantic discriminated unions, why an allowlist flips its server to default-deny, hot-reload-ready compilation, the Redis rate-limit seam |
| 17 | [fail-closed-policy-enforcement.md](17-fail-closed-policy-enforcement.md) | Why a policy denial is a JSON-RPC error not an HTTP error, fail-closed on policy-engine exceptions, what policy governs (tools/call only) vs. what bypasses it |
| 18 | [postgres-sqlalchemy-alembic.md](18-postgres-sqlalchemy-alembic.md) | Why a real database now, what an ORM buys you, migrations as a version-controlled paper trail for schema changes, one shared DB-URL setting |
| 19 | [hash-chained-audit-log.md](19-hash-chained-audit-log.md) | What tamper-evidence means and how a hash chain achieves it, the genesis hash, why one call can produce two append-only rows, the advisory-lock concurrency fix, app-clock vs. DB-server-time tradeoff |
| 20 | [cli-with-typer.md](20-cli-with-typer.md) | Why Typer needed no new dependency, the single-command-collapses-the-CLI gotcha, why `--since` filters the report but never skips verifying earlier history |

More get added as we build — each new one lands here the day it's created.
