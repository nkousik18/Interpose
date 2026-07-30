"""Unit tests for the Recommendation node: risk-to-disposition mapping and handling
both outcomes `mark_investigated` can resolve to today -- success, or a
`ToolCallError` (the shape a future policy DENY would also take, once the AML pack's
`aml-write-hitl-gate.yaml` exists -- Day 14)."""

from unittest.mock import AsyncMock

import pytest
from aml_investigator.gateway_client import ToolCallError
from aml_investigator.nodes.recommendation import make_recommendation_node
from aml_investigator.state import Alert, Assessment, InvestigationState


def _assessed_state(risk_level: str) -> InvestigationState:
    return InvestigationState(
        alert=Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE"),
        assessment=Assessment(risk_level=risk_level, key_findings=["x"], rationale="because"),
    )


@pytest.mark.parametrize(
    ("risk_level", "expected_disposition"),
    [("high", "escalate"), ("medium", "monitor"), ("low", "cleared")],
)
async def test_maps_risk_level_to_disposition(risk_level: str, expected_disposition: str) -> None:
    client = AsyncMock()
    client.mark_investigated.return_value = {"disposition": expected_disposition}
    node = make_recommendation_node(client)

    update = await node(_assessed_state(risk_level))

    assert update["recommendation"].disposition == expected_disposition
    client.mark_investigated.assert_awaited_once_with(
        "1:ACC001", expected_disposition, "because"
    )


async def test_records_write_result_on_success() -> None:
    client = AsyncMock()
    client.mark_investigated.return_value = {"disposition": "cleared", "recorded_at": "now"}
    node = make_recommendation_node(client)

    update = await node(_assessed_state("low"))

    assert update["recommendation"].write_result == {"disposition": "cleared", "recorded_at": "now"}
    assert update["recommendation"].write_error is None


async def test_records_write_error_without_raising_when_the_write_is_denied() -> None:
    client = AsyncMock()
    client.mark_investigated.side_effect = ToolCallError("denied by policy aml-write-hitl-gate")
    node = make_recommendation_node(client)

    update = await node(_assessed_state("high"))

    assert update["recommendation"].write_result is None
    assert "denied" in update["recommendation"].write_error
