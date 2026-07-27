"""OpenTelemetry tracing setup (docs/INTERPOSE_SCOPING.md Section 11.8, gate S3).

Three of the gateway's real stages already have a library that can auto-instrument
them for free -- the incoming HTTP request (FastAPI), the outbound forward call to
the upstream MCP server (httpx), and the audit-log writes (SQLAlchemy) -- so this
module wires those three up rather than hand-writing spans a library already knows
how to produce. Policy evaluation (`interpose.gateway.app._compile_and_evaluate`) is
pure in-process Python with no library to instrument, so the gateway wraps that one
call in a manual span itself -- see its call site in `app.py`.

Split into two entry points, `setup_tracing` and `instrument_sqlalchemy_engine`,
because they have genuinely different timing requirements, not for abstraction's own
sake: `setup_tracing` must run immediately after the FastAPI app object is created and
before it handles its first ASGI event (lifespan startup included) --
`FastAPIInstrumentor.instrument_app` works by patching
`Starlette.build_middleware_stack`, which Starlette calls (and caches the result of)
exactly once, on the app's first `__call__`. Calling `instrument_app` from *inside*
the lifespan -- which runs as part of that first `__call__` -- patches the method
after the cache is already populated, so the patch has no effect and nothing gets
instrumented; this was caught by the Day 10 live Jaeger check (spans existed but
every one was its own disconnected trace, never nested under a request root).
`instrument_sqlalchemy_engine`, in contrast, has no such ordering constraint -- it
just needs the engine, which the lifespan only creates once it starts -- so it's
called from there instead.

Deliberately opt-in (`Settings.otel_exporter_endpoint` defaults to `None`, see
`config.py`): skipping setup entirely when unset means a kind deployment with no
collector reachable doesn't start a background export thread that will only ever fail
to connect. See concepts/27-opentelemetry-and-distributed-tracing.md for what a span/
trace/OTLP actually are, and why this is a different "trace"/"span" than the
UUID columns already on `audit_entries` (concepts/19-hash-chained-audit-log.md).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_TRACER_NAME = "interpose.gateway"


def setup_tracing(app: FastAPI, otlp_endpoint: str) -> TracerProvider:
    """Call once, right after `FastAPI(...)` is constructed -- before returning the
    app, before the lifespan runs. Sets the process-global TracerProvider (every other
    instrumentor, and `get_tracer()`, use whatever is globally registered) and
    instruments FastAPI (root span per HTTP request) and httpx (child span per
    outbound request -- the gateway -> upstream MCP server hop).

    Returns the TracerProvider so the lifespan can `.shutdown()` it on teardown --
    that flushes any spans still sitting in the batch processor's buffer rather than
    dropping them.
    """
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "interpose-gateway"}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    logger.info("tracing.started otlp_endpoint=%s", otlp_endpoint)
    return provider


def instrument_sqlalchemy_engine(engine: AsyncEngine) -> None:
    """Call once the lifespan has created the audit engine. Hooks SQLAlchemy core's
    cursor-execute events, which live on the sync engine an AsyncEngine wraps --
    instrumenting the AsyncEngine object itself is a no-op."""
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def get_tracer() -> trace.Tracer:
    """Safe to call even when `setup_tracing` was never invoked -- the OTel API
    returns a no-op tracer against the default provider, so spans created from it are
    simply discarded rather than raising."""
    return trace.get_tracer(_TRACER_NAME)
