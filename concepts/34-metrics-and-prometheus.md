# Metrics and Prometheus: closing the last named gap

Follows [[27-opentelemetry-and-distributed-tracing]]. Closes the third of Phase 3
Day 15's three named gaps (`docs/project/SESSION_LOG.md`): "no Prometheus/`/metrics`
-- Dashboard 1 (Gateway Health) remains an approximation."

## What "an approximation" meant

Dashboard 1 was always meant to show real-time golden-signal metrics (Section 12.3:
rate, errors, duration, saturation, plus a custom policy-fires signal) via
Prometheus. None of that existed, so Dashboard 1 instead queried
`agg_telemetry_hourly` -- a Postgres table Spark built from the audit log's own
`status`/`latency_ms` columns (Day 15). That's real request data, just sourced from
the audit trail, over a *fixed* historical window (a one-time synthetic corpus, not a
live feed) -- not what a "gateway health" dashboard operators actually watch during
an incident is supposed to look like.

## Why an OTel Collector, not `prometheus_client` + a `/metrics` endpoint

The obvious-looking alternative -- add `prometheus_client` to the gateway, expose a
`/metrics` endpoint, point Prometheus straight at the pod -- would work. But this
project already has a working OpenTelemetry *tracing* pipeline
([[27-opentelemetry-and-distributed-tracing]]): the gateway exports OTLP over gRPC,
today to Jaeger in bare local dev. OpenTelemetry's metrics API uses the exact same
export mechanism (an OTLP endpoint, the same `Settings.otel_exporter_endpoint`), and a
real OTel Collector accepts both signals on the same port. Reusing that pipeline means
one dependency set and one mental model, instead of maintaining two parallel
instrumentation libraries that happen to both call themselves "observability."

The Collector sits in the middle specifically because Prometheus can't consume OTLP
metrics directly -- it scrapes a `/metrics`-shaped HTTP endpoint on its own schedule.
The Collector's `prometheus` exporter is the adapter: receive OTLP push, expose a
`/metrics`-shaped pull endpoint, on port 8889 in this chart
(`charts/interpose/templates/otel-collector/`).

## The five instruments, and how OTel instrument types become Prometheus types

`src/interpose/observability/metrics.py` defines exactly Section 12.3's five named
metrics. Three OTel instrument types cover all five:

| Metric | OTel instrument | Why that type |
|---|---|---|
| `interpose_tool_calls_total` | Counter | Only ever increases -- a running count of calls. |
| `interpose_tool_call_errors_total` | Counter | Same reasoning, scoped to errors. |
| `interpose_policy_fires_total` | Counter | Same reasoning, scoped to policy activations. |
| `interpose_tool_call_duration_seconds` | Histogram | Needs a distribution (p50/p95/p99), not just a total. |
| `interpose_gateway_inflight` | UpDownCounter | Can go up *and* down -- a call finishing decrements it. |

`UpDownCounter` is the one non-obvious choice. OTel also has an "asynchronous gauge"
(a registered callback that reports whatever the current value is when the SDK asks),
which sounds like the natural fit for "concurrent in-flight calls" -- but that shape
doesn't match how the gateway actually knows this number: it's not queryable on
demand, it's an increment-on-start/decrement-on-end running total, which is exactly
what an `UpDownCounter` is for. The Collector's Prometheus exporter renders it as a
Prometheus gauge on export either way, so Grafana sees the same shape regardless of
which OTel instrument produced it.

## Where the five instruments get called

All five are recorded from `src/interpose/gateway/app.py`, at the points that already
compute the values -- no new tracking state:

- **Saturation + duration** wrap the entire `_handle_tool_call` call (policy
  evaluation, any HITL wait, the upstream forward) at its one call site in
  `proxy_mcp`, not threaded through every nested return branch inside it. That's a
  deliberate scope choice: "in flight" should mean the whole time a caller is waiting
  on a response, including a multi-minute HITL hold, not just the final upstream
  round trip.
- **Tool calls total** (by outcome) and **errors total** are recorded at each
  existing terminal-outcome branch (`policy_denied`, `hitl_timeout`, `hitl_denied`,
  `upstream_error`, `completed`) -- right next to the `logger.warning`/`logger.info`
  call that already marks that same moment.
- **Policy fires total** is recorded once per entry in `policies_fired`, right after
  policy evaluation returns -- reusing the *exact* list already written to
  `audit_entries.policies_fired` on every audit row, not a stricter or looser
  definition of "fired." Whatever that column has always meant, this metric means
  the same thing.

## The embedded-vs-external split, one more time

Same pattern as Postgres/Redis ([[26-helm-and-the-interpose-chart]]): `values.yaml`'s
production-leaning defaults turn `otelCollector.enabled`/`prometheus.enabled` off --
Section 11.8 says production deployments bring their own observability backend, and a
chart that silently stands up a demo-grade, no-persistent-storage Prometheus inside
someone's real cluster would be the wrong default. `values-dev.yaml` turns both on,
matching how it already makes the local kind install fully self-contained.

An `otelExporterEndpoint` value still exists for the case where a production operator
*does* want the gateway to export somewhere -- their own already-running Collector --
without the chart deploying one itself. `interpose.otelExporterEndpoint` (the Helm
template helper) picks `otelCollector`'s in-cluster address when the chart deployed
one, otherwise falls back to that value, otherwise resolves empty (no
`OTEL_EXPORTER_ENDPOINT` env var at all -- tracing and metrics setup both stay
skipped, exactly `Settings.otel_exporter_endpoint`'s existing "None means off"
behavior, unchanged from before this component existed).

## What's still a named gap after this

Traces still have no real in-cluster destination -- the Collector's traces pipeline
exports to its own `debug` log (stdout) rather than a real backend, since no
Jaeger/Tempo/Honeycomb is deployed in the chart. That's an honest placeholder, not a
claim that traces are queryable in-cluster; bare local dev (`docker-compose.yaml`'s
Jaeger) is still the only place a trace can actually be viewed end-to-end.

Bare local dev also doesn't get live metrics: `Settings.otel_exporter_endpoint` is one
shared setting for both signals, and locally it points at Jaeger, which has no
metrics receiver. Periodic metric export attempts there fail and log a warning every
export interval rather than crashing the app -- a real, named tradeoff of reusing one
endpoint for two signals, not silently papered over. Live Prometheus metrics are an
in-cluster-only capability today.
