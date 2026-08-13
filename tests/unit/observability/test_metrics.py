"""Unit tests for `interpose.observability.metrics` -- the pure, no-network-needed
half. `setup_metrics` itself needs a real OTLP endpoint to meaningfully verify
(exercised live against a real OTel Collector, not here -- same "verify live, don't
just unit-test" split this project's own OTel tracing setup already follows, since
neither module has a fake/mock exporter to substitute).

What *is* unit-testable without any of that: every `record_*`/`inflight_*` function
must be safe to call even when `setup_metrics` was never invoked -- the default,
no-op `MeterProvider` the OTel API falls back to -- since that's exactly gateway
`app.py`'s own behavior whenever `OTEL_EXPORTER_ENDPOINT` is unset (dev/test default).
"""

from interpose.observability import metrics


def test_record_tool_call_is_safe_without_setup_metrics() -> None:
    metrics.record_tool_call(server="hello-echo", tool="echo", outcome="completed")


def test_record_tool_call_error_is_safe_without_setup_metrics() -> None:
    metrics.record_tool_call_error(error_type="upstream_unreachable")


def test_record_tool_call_duration_is_safe_without_setup_metrics() -> None:
    metrics.record_tool_call_duration(server="hello-echo", tool="echo", seconds=0.042)


def test_inflight_start_and_end_are_safe_without_setup_metrics() -> None:
    metrics.inflight_start()
    metrics.inflight_end()


def test_record_policy_fire_is_safe_without_setup_metrics() -> None:
    metrics.record_policy_fire(
        policy_name="hello-echo-denylist", effect_type="denylist", outcome="deny"
    )


def test_instruments_are_created_once_and_reused() -> None:
    first = metrics._get_instruments()
    second = metrics._get_instruments()
    assert first is second
