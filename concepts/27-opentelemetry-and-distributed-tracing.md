# OpenTelemetry: distributed tracing, and why it's a different "trace" than the audit log's

Phase 2 Day 10 (`docs/ROADMAP.md`); implements `docs/INTERPOSE_SCOPING.md` Section 11.8's
tracing piece, gate S3 ("render a trace of a single tool call end-to-end").

## The problem this solves

A single `tools/call` through the gateway touches several things in sequence: FastAPI
parses the HTTP request, the policy engine evaluates it, the audit store writes a row
to Postgres, httpx forwards the call to the upstream MCP server, another audit write
happens on the way back. When that call is slow, or fails, "where" is a real
question -- was it the policy engine? The DB write? The upstream itself? Logs answer
this if you're willing to grep timestamps across several log lines by hand. A
**distributed trace** answers it directly: one **trace** per request, made of nested
**spans** — one per unit of work, each with a start time, a duration, and a parent —
so a single view shows exactly which step took how long, in order, nested correctly.
"Distributed" because the same trace ID can span process boundaries (gateway →
upstream MCP server), not just function calls inside one process.

## OpenTelemetry, OTLP, and Jaeger — what's whose job

**OpenTelemetry (OTel)** is a vendor-neutral standard (API + SDK) for producing
traces (also metrics and logs, not used here yet). "Vendor-neutral" is the whole
point: the gateway's code creates spans against OTel's API; where those spans *go* is
a separate, swappable concern. **OTLP** (OpenTelemetry Protocol) is the wire format
spans get exported in. **Jaeger** is one of many OTLP-compatible backends that store
and let you query traces — Tempo, Honeycomb, Datadog are others; Section 11.8 names
Jaeger for local dev specifically because enterprise buyers can point their own
existing backend at the same OTLP export in production instead.

## Auto-instrumentation: three real spans without writing any span code

Three of the gateway's stages already have an OTel *instrumentor* — a small library
that hooks a popular package's internals and emits spans automatically, with zero
code changes at the call site:

- **FastAPI** (`FastAPIInstrumentor`): one root span per incoming HTTP request.
- **httpx** (`HTTPXClientInstrumentor`): one child span per outbound request — this is
  what actually shows the gateway → upstream MCP server hop.
- **SQLAlchemy** (`SQLAlchemyInstrumentor`): one child span per DB query — the audit
  `INTENT`/`COMPLETED` writes. Instruments `engine.sync_engine`, not the `AsyncEngine`
  wrapper itself — the instrumentor hooks SQLAlchemy core's cursor-execute events,
  which live underneath the async wrapper, not on it.

`interpose.observability.tracing.setup_tracing()` wires all three at gateway startup.
That alone produces a real, correctly-nested trace for a tool call with no manual
span-writing at all.

## The one manual span: policy evaluation

Policy evaluation (`_compile_and_evaluate` in `gateway/app.py`) is plain in-process
Python — no library "does the work" the way FastAPI/httpx/SQLAlchemy do, so nothing
auto-instruments it. That's the one place the gateway wraps a call in a span by hand:

```python
with get_tracer().start_as_current_span("policy.evaluate") as span:
    span.set_attribute("interpose.server", server_name)
    ...
    decision, policies_fired = _compile_and_evaluate(...)
    span.set_attribute("interpose.decision", decision.outcome.name)
```

`get_tracer()` is safe to call unconditionally, even when tracing was never set up
(`otel_exporter_endpoint` unset): OTel's API returns a no-op tracer against the
default provider in that case, so the `with` block still runs, just producing nothing
— the same "off unless configured" shape as `groq_api_key`.

## This is not the audit log's `trace_id`/`span_id`

`audit_entries` already has `trace_id`/`span_id`/`parent_id` columns
([[19-hash-chained-audit-log]]) — easy to assume this is the same tracing. It isn't.
Those are plain UUIDs the gateway generates itself, purely to link an `INTENT` row to
its later `COMPLETED` row (via `parent_id` — that's the column the code actually
queries by; `trace_id` is shared across the pair mostly for future convenience). They
exist for audit correlation: proving which two database rows describe the same
logical call, forever, as part of a tamper-evident record. OTel's trace/span IDs
exist for operator observability: transient, exported to Jaeger, gone once nobody's
looking. Same words, two unrelated systems, serving two different audiences
(auditor vs. on-call engineer) — worth keeping straight rather than assuming one
subsumes the other.

## What's deferred

- **No OTel Collector or Jaeger in the Helm chart** — `docker-compose.yaml` runs
  Jaeger for bare/local dev; a kind install leaves `otel_exporter_endpoint` unset, so
  the gateway pod traces nothing. Section 11.8's real target (a Collector DaemonSet)
  is Phase 3/4 scope, once there's a second in-cluster service worth correlating
  traces across.
- **No control-plane agent spans** — the LangGraph agents (Day 7/8) aren't
  instrumented yet; today's trace covers the gateway's synchronous request path only.
- **No metrics** — Prometheus/RED metrics are a separate, still-fully-deferred piece
  of Section 11.8 (see `charts/interpose/README.md`'s named-gaps table).

## Related

- [[19-hash-chained-audit-log]]
- [[15-fastapi-and-the-naive-proxy]]
- [[18-postgres-sqlalchemy-alembic]]
- [[26-helm-and-the-interpose-chart]]
