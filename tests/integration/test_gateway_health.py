"""Phase 2 Day 9: the Helm chart's liveness/readiness probes hit these for real
(Section 11.5), so they need to be genuinely correct against real Postgres + Redis,
not stubbed 200s -- a probe that always reports healthy is worse than no probe.
"""

import httpx


async def test_healthz_always_ok(upstream_and_gateway: None) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8000/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_postgres_and_redis_reachable(upstream_and_gateway: None) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8000/readyz")
    assert response.status_code == 200
    assert response.json() == {"postgres": True, "redis": True}
