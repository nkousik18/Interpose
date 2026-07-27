# Standalone image for the trivial upstream MCP server, deployed in-cluster via
# dev/mcp-servers/hello-echo.yaml so the kind-deployed gateway has a real MCP server
# to route to end-to-end (Phase 2 Day 10). Deliberately its own tiny image, not a
# COPY of examples/ into the main interpose:dev image -- this fixture doesn't need
# any of the gateway's dependencies (Postgres, Redis, LangGraph, ...), just the mcp
# SDK, so bundling it into the app image would mean shipping unrelated weight for
# something that isn't the app under test.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
RUN uv pip install --system --no-cache "mcp[cli]>=1.28.1"

RUN groupadd --gid 10001 echo && \
    useradd --uid 10001 --gid echo --no-create-home --shell /usr/sbin/nologin echo

COPY --chown=echo:echo server.py .

# See server.py's MCP_ECHO_HOST comment: 0.0.0.0 is required for a Kubernetes Service
# to reach this pod at all.
ENV MCP_ECHO_HOST=0.0.0.0
USER echo
EXPOSE 9001

CMD ["python", "server.py"]
