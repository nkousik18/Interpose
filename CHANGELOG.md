# Changelog

All notable changes to this project are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/) once it reaches `v0.1.0`.

## [Unreleased]

### Added
- Repo scaffold per `docs/INTERPOSE_SCOPING.md` Section 6.16 (`src/interpose/`, `mcp-servers/`,
  `agents/`, `charts/`, `terraform/`, `policies/`, `tests/`).
- Local dev environment: `uv`-managed Python 3.12, Docker, `kubectl`, `helm`, `terraform`,
  `kind` — installed and verified end-to-end.
- `concepts/` — plain-language explainers, added incrementally as the project introduces new
  tools and domain concepts.
- OFAC SDN sanctions list downloaded and validated (19,169 entries).
- IBM AML (HI-Medium) dataset downloaded from Kaggle (31.9M transaction rows); subsampling
  pending.
- MCP Python SDK hello-world (`examples/hello-mcp-echo/`) — verified client/server round trip
  over the stdio transport.
- CI (GitHub Actions): lint (`ruff`) + test (`pytest`) on push/PR to `main`.
- Standard OSS community-health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`,
  issue/PR templates.

### Changed
- Project renamed from "Sentinel" to "Interpose" (repo, package, docs) — see commit history.
