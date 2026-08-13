"""OpenTelemetry metrics setup (docs/INTERPOSE_SCOPING.md Section 12.3, closing the
"no Prometheus/`/metrics`" named gap left open by Phase 3 Day 15 -- see
`docs/project/SESSION_LOG.md`).

Reuses the same OTLP pipeline [[27-opentelemetry-and-distributed-tracing]] already
wired up for tracing, rather than a separate `prometheus_client` integration and a
hand-rolled `/metrics` endpoint: an OTel Collector in the chart receives both traces
and metrics on the same OTLP gRPC port, and its Prometheus exporter turns the metrics
half into something Prometheus can scrape -- one pipeline, one dependency set,
instead of two parallel instrumentation libraries. See
`concepts/34-metrics-and-prometheus.md` for the full reasoning and the OTel-instrument
to Prometheus-metric-type mapping.

Five instruments, matching Section 12.3's golden-signal table exactly:

| Signal | Instrument | OTel type |
|---|---|---|
| Rate | `interpose_tool_calls_total` | Counter |
| Errors | `interpose_tool_call_errors_total` | Counter |
| Duration | `interpose_tool_call_duration_seconds` | Histogram |
| Saturation | `interpose_gateway_inflight` | UpDownCounter |
| Policy fires | `interpose_policy_fires_total` | Counter |

`interpose_gateway_inflight` is an `UpDownCounter`, not an OTel "asynchronous gauge"
(the closer-sounding name): a gauge is callback-based (you register a function that
reports the *current* value when asked), which doesn't fit "increment when a call
starts, decrement when it ends" at all. An `UpDownCounter` is exactly that -- a
running total nothing has ever restricted to only increasing -- and the OTel
Collector's Prometheus exporter already renders it as a Prometheus gauge on export, so
the *result* Prometheus sees is a gauge either way.

Deliberately reuses `Settings.otel_exporter_endpoint` rather than a second endpoint
setting -- same value tracing already uses, since a real OTel Collector's OTLP
receiver accepts both signals on the same port. In bare local dev, that setting still
points at Jaeger (`docker-compose.yaml`), which has no metrics receiver: periodic
metric export attempts there will fail and log a warning every export interval, not
crash the app (`PeriodicExportingMetricReader` catches per-export failures) -- an
honest, named limitation of reusing one endpoint for two signals, not silently papered
over. Live metrics via Prometheus are an in-cluster-only capability for now; see
`concepts/34-metrics-and-prometheus.md`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

logger = logging.getLogger(__name__)

_METER_NAME = "interpose.gateway"
# Short enough that a demo/dev session sees the dashboard update within a few
# seconds of real traffic, not the SDK's 60s default -- this is a metrics pipeline
# meant to be watched live during a demo, not a low-overhead production scrape.
_EXPORT_INTERVAL_MILLIS = 5_000


def setup_metrics(otlp_endpoint: str) -> MeterProvider:
    """Call once, from the gateway lifespan (no `setup_tracing`-style ordering
    constraint here -- metrics aren't tied to Starlette's middleware-stack caching).
    Returns the MeterProvider so the lifespan can `.shutdown()` it on teardown,
    flushing any metrics still sitting in the exporter's buffer."""
    resource = Resource.create({SERVICE_NAME: "interpose-gateway"})
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=_EXPORT_INTERVAL_MILLIS,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    logger.info("metrics.started otlp_endpoint=%s", otlp_endpoint)
    return provider


def _meter() -> metrics.Meter:
    """Safe to call even when `setup_metrics` was never invoked -- same reasoning as
    `tracing.get_tracer`: the OTel API returns a no-op meter against the default
    provider, so every instrument created from it is a no-op rather than raising."""
    return metrics.get_meter(_METER_NAME)


@dataclass(frozen=True)
class _Instruments:
    tool_calls_total: metrics.Counter
    tool_call_errors_total: metrics.Counter
    tool_call_duration_seconds: metrics.Histogram
    gateway_inflight: metrics.UpDownCounter
    policy_fires_total: metrics.Counter


_instruments: _Instruments | None = None


def _get_instruments() -> _Instruments:
    """Instruments are meant to be created once and reused (the OTel SDK docs'
    own guidance) -- creating a fresh Counter object per request would work
    functionally, but building the underlying aggregation state on every call is
    needless overhead on the gateway's hot path. Lazy, not module-import-time,
    so a test importing this module doesn't need a MeterProvider configured yet."""
    global _instruments
    if _instruments is None:
        meter = _meter()
        _instruments = _Instruments(
            tool_calls_total=meter.create_counter(
                "interpose_tool_calls_total",
                description="Tool calls, per {server, tool, outcome}.",
            ),
            tool_call_errors_total=meter.create_counter(
                "interpose_tool_call_errors_total",
                description="Tool call errors, per {error_type}.",
            ),
            tool_call_duration_seconds=meter.create_histogram(
                "interpose_tool_call_duration_seconds",
                unit="s",
                description="End-to-end tool call duration, per {server, tool}.",
            ),
            gateway_inflight=meter.create_up_down_counter(
                "interpose_gateway_inflight",
                description="Concurrent in-flight tool calls.",
            ),
            policy_fires_total=meter.create_counter(
                "interpose_policy_fires_total",
                description="Policy activations, per {policy_name, effect_type, outcome}.",
            ),
        )
    return _instruments


def record_tool_call(*, server: str, tool: str, outcome: str) -> None:
    _get_instruments().tool_calls_total.add(1, {"server": server, "tool": tool, "outcome": outcome})


def record_tool_call_error(*, error_type: str) -> None:
    _get_instruments().tool_call_errors_total.add(1, {"error_type": error_type})


def record_tool_call_duration(*, server: str, tool: str, seconds: float) -> None:
    _get_instruments().tool_call_duration_seconds.record(seconds, {"server": server, "tool": tool})


def inflight_start() -> None:
    _get_instruments().gateway_inflight.add(1)


def inflight_end() -> None:
    _get_instruments().gateway_inflight.add(-1)


def record_policy_fire(*, policy_name: str, effect_type: str, outcome: str) -> None:
    """One call per entry in a `policies_fired` list (the same list already written
    to `audit_entries.policies_fired` -- see that column's docstring) -- this metric
    uses the exact same "fired" semantics the audit log already established: every
    policy applicable to this {server, tool}, not only the one that determined the
    final outcome."""
    _get_instruments().policy_fires_total.add(
        1, {"policy_name": policy_name, "effect_type": effect_type, "outcome": outcome}
    )
