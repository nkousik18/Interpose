# Standalone image for the OFAC sanctions MCP server (docs/INTERPOSE_SCOPING.md
# Section 9.6, Phase 3 Day 11). Its own tiny image, not folded into the main
# interpose:dev image or example servers -- this is meant to be a genuinely separate
# service, the way a real production sanctions-screening API would be, and it needs
# none of the gateway's own dependencies (Postgres, Redis, LangGraph, ...).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
# mcp is pinned exactly (matching the root project's uv.lock), not left as a
# lower-bound ">=" -- this standalone Dockerfile has no lockfile of its own, so an
# unpinned install silently drifts to whatever's newest on PyPI at build time. Found
# for real while building transaction-graph's Dockerfile (Phase 3 Day 12): a fresh
# build on 2026-07-28 resolved mcp[cli]==2.0.0, a breaking upstream major version that
# renamed/removed `mcp.server.fastmcp` -- this image would fail identically on a
# rebuild today even though it worked at Day 11. See
# concepts/29-embedded-analytics-with-duckdb.md.
RUN uv pip install --system --no-cache "mcp[cli]==1.28.1" "rapidfuzz>=3.10" \
    "pydantic-settings>=2.5" "httpx>=0.28"

RUN groupadd --gid 10001 ofac && \
    useradd --uid 10001 --gid ofac --no-create-home --shell /usr/sbin/nologin ofac

COPY --chown=ofac:ofac src/ .

# 0.0.0.0 is required for a Kubernetes Service to reach this pod at all -- same
# reasoning as the gateway's GATEWAY_HOST and the echo server's MCP_ECHO_HOST.
# sdn_source/alt_source are left at their real-Treasury-URL defaults (config.py) --
# this container genuinely fetches the live list on every start, same as the real
# service it stands in for.
ENV OFAC_HOST=0.0.0.0
USER ofac
EXPOSE 9002

CMD ["python", "server.py"]
