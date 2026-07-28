# Standalone image for the transaction-graph MCP server (docs/INTERPOSE_SCOPING.md
# Section 9.6, Phase 3 Day 12). Same reasoning as ofac-sanctions/Dockerfile: its own
# tiny image, not folded into the main interpose:dev image -- a genuinely separate
# service, the way a real production transaction-graph API would be.
#
# Unlike ofac-sanctions (which fetches its reference data live from a public API),
# this server's data is a large (~150MB) local Parquet dataset that is never
# committed to the repo or baked into the image (data/README.md) -- it's bind-mounted
# at *run* time instead. See README.md for the `docker run -v ...` invocation.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
# mcp is pinned exactly (matching the root project's uv.lock), not left as a
# lower-bound ">=" -- a standalone service Dockerfile like this one has no lockfile
# of its own, so an unpinned install silently drifts to whatever's newest on PyPI at
# build time. Caught for real: building this image on 2026-07-28 resolved
# mcp[cli]==2.0.0, a breaking upstream major version that renamed/removed
# `mcp.server.fastmcp` (replaced by `mcp.server.mcpserver`) -- `import
# FastMCP` failed at container startup. See
# concepts/29-embedded-analytics-with-duckdb.md.
RUN uv pip install --system --no-cache "mcp[cli]==1.28.1" "duckdb>=1.1" "pydantic-settings>=2.5"

RUN groupadd --gid 10002 txgraph && \
    useradd --uid 10002 --gid txgraph --no-create-home --shell /usr/sbin/nologin txgraph

COPY --chown=txgraph:txgraph src/ .

# 0.0.0.0 is required for a Kubernetes Service to reach this pod at all -- same
# reasoning as the gateway's GATEWAY_HOST and ofac-sanctions' OFAC_HOST.
# TRANSACTION_GRAPH_TRANSACTIONS_SOURCE / _ACCOUNTS_SOURCE are left unset here on
# purpose -- the caller must bind-mount the data and set both to point inside the
# container (see README.md), there's no sane baked-in default the image itself can
# supply.
ENV TRANSACTION_GRAPH_HOST=0.0.0.0
USER txgraph
EXPOSE 9003

CMD ["python", "server.py"]
