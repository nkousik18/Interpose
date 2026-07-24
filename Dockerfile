# Interpose gateway image. One image, two things run from it:
#   - the gateway process itself (`python -m interpose.gateway`, includes the
#     in-process control-plane loop -- see docs/ROADMAP.md Day 9 for why this is one
#     Deployment, not the two Section 11.5 describes)
#   - the Alembic migration Helm hook Job (charts/interpose/templates/migrate-job.yaml),
#     which needs the same dependencies plus alembic/ and alembic.ini
#
# Multi-stage: the builder stage has uv and compiles the dependency set once into a
# venv; the runtime stage copies just that venv + source, so the final image doesn't
# carry uv, pip caches, or build toolchains.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first, isolated from source changes, so editing application code
# doesn't invalidate this layer's cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

# Non-root by default (basic Docker hygiene). The fuller Section 11.5 pod-security
# hardening -- distroless base, readOnlyRootFilesystem, seccomp profile -- is a named,
# deferred gap (see docs/ROADMAP.md Day 9): none of it is exercised by anything running
# today, and getting a distroless base wrong silently (e.g. no shell for `alembic`'s
# migration job to run in) is a worse failure mode than shipping slim-but-rootless now.
RUN groupadd --gid 10001 interpose && \
    useradd --uid 10001 --gid interpose --no-create-home --shell /usr/sbin/nologin interpose

WORKDIR /app
COPY --from=builder --chown=interpose:interpose /app /app
# config/upstreams.yaml and config/policies/ baked in as a self-contained fallback
# (`docker run` works standalone without a ConfigMap mount) -- the chart's ConfigMap
# volume mounts at this same path and shadows these defaults entirely inside the
# cluster, so there's no drift risk between "baked-in default" and "what's deployed".
COPY --chown=interpose:interpose config ./config

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    # Loopback-only is correct for bare `uv run` on a developer's host (config.py's
    # default) but never correct inside a container -- nothing outside the container's
    # network namespace could ever reach 127.0.0.1, docker -p / k8s Service included.
    GATEWAY_HOST=0.0.0.0

USER interpose
EXPOSE 8000

CMD ["python", "-m", "interpose.gateway"]
