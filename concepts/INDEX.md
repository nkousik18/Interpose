# Concepts index

Plain-language explainers, one concept per file, added as the Sentinel project introduces new
ideas. See the root `CLAUDE.md` for the rules these follow. Numbered roughly in the order each
concept was introduced.

| # | File | What it covers |
|---|------|-----------------|
| 00 | [claude-md-files.md](00-claude-md-files.md) | What a `CLAUDE.md` file is and why this repo has one |
| 01 | [what-is-mcp.md](01-what-is-mcp.md) | The Model Context Protocol: tools, servers, clients |
| 02 | [sentinel-gateway-overview.md](02-sentinel-gateway-overview.md) | What Sentinel is, why it's a proxy, the three "planes" |
| 03 | [sla-slo-latency-budgets.md](03-sla-slo-latency-budgets.md) | SLA vs SLO vs SLI, and why latency targets are stated as percentiles |
| 04 | [aml-ofac-glossary.md](04-aml-ofac-glossary.md) | AML/KYC/OFAC/SAR/structuring/HITL vocabulary for the demo domain |
| 05 | [python-envs-and-uv.md](05-python-envs-and-uv.md) | Python version/dependency management, why `uv`, and a Homebrew autoremove lesson |
| 06 | [containers-and-docker.md](06-containers-and-docker.md) | What a container is, what Docker actually does, why Sentinel needs it |
| 07 | [what-is-kubernetes.md](07-what-is-kubernetes.md) | What Kubernetes orchestrates, and how kubectl/kind fit together |
| 08 | [terraform-and-iac.md](08-terraform-and-iac.md) | Infrastructure as Code, what Terraform's job is here vs. Helm |
| 09 | [mcp-handshake-and-transports.md](09-mcp-handshake-and-transports.md) | stdio vs. HTTP transports, and the initialize/list_tools/call_tool handshake, from a real run |
| 10 | [open-data-licensing.md](10-open-data-licensing.md) | Public domain vs. CC-BY vs. CDLA-Sharing, and why we had to correct the scoping doc |

More get added as we build — each new one lands here the day it's created.
