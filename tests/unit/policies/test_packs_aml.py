"""Unit tests for interpose.policies.packs.aml -- the AML pack's two custom policy
hooks (Phase 3 Day 14). `aml_structuring_alert` (response-side) is fully unit-testable
with a fake Redis. `aml_sanctions_required` (request-side) queries the audit log via a
real `async_sessionmaker` and isn't meaningfully testable without a real Postgres --
same reasoning as Agent A1's own DB-backed feature computation
(tests/unit/control_plane/test_policy_evaluator.py); it's exercised for real in
tests/integration/test_investigation_agent_aml_pack.py.
"""

from unittest.mock import AsyncMock

from interpose.policies.custom import ResponsePolicyContext
from interpose.policies.packs.aml import FORCE_HITL_TTL_SECONDS, aml_structuring_alert
from interpose.policies.schema import Policy

_POLICY = Policy.model_validate(
    {
        "policy": "aml-structuring-alert",
        "applies_to": {"server": "transaction-graph", "tools": ["structuring_check"]},
        "effect": {"type": "custom", "name": "aml_structuring_alert", "stage": "response"},
    }
)


def _context(response_payload: object, redis: AsyncMock) -> ResponsePolicyContext:
    return ResponsePolicyContext(
        session_id="sess-1",
        server="transaction-graph",
        tool="structuring_check",
        arguments={"account_id": "1:ACC001"},
        response_payload=response_payload,
        redis=redis,
    )


class TestAmlStructuringAlert:
    async def test_does_nothing_when_not_flagged(self) -> None:
        redis = AsyncMock()
        tags = await aml_structuring_alert(_POLICY, _context({"flagged": False}, redis))
        assert tags == []
        redis.set.assert_not_awaited()

    async def test_does_nothing_for_a_non_dict_payload(self) -> None:
        redis = AsyncMock()
        tags = await aml_structuring_alert(_POLICY, _context(None, redis))
        assert tags == []
        redis.set.assert_not_awaited()

    async def test_sets_the_force_hitl_flag_and_tags_the_incident_when_flagged(self) -> None:
        redis = AsyncMock()
        tags = await aml_structuring_alert(_POLICY, _context({"flagged": True}, redis))

        assert tags == ["incident:structuring", "severity:high"]
        redis.set.assert_awaited_once_with(
            "interpose:session:sess-1:force_hitl",
            "aml_structuring_alert",
            ex=FORCE_HITL_TTL_SECONDS,
        )
