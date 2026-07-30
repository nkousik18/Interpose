"""Unit tests for agents/aml-investigator/src/aml_investigator/gateway_client.py's
`_call` envelope-unwrapping and error-handling logic. A fake `ClientSession` is
injected directly into `_sessions` (bypassing `__aenter__`, which opens a real
streamable-HTTP connection) -- the live, real-server version of this is exercised in
tests/integration/test_investigation_agent.py.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aml_investigator.gateway_client import (
    OFAC_ROUTE,
    TRANSACTION_GRAPH_ROUTE,
    InvestigationClient,
    ToolCallError,
)


def _ok_result(structured_content: object) -> SimpleNamespace:
    return SimpleNamespace(isError=False, content=[], structuredContent=structured_content)


def _error_result(message: str) -> SimpleNamespace:
    return SimpleNamespace(
        isError=True, content=[SimpleNamespace(text=message)], structuredContent=None
    )


def _client_with_fake_session(result: object) -> tuple[InvestigationClient, AsyncMock]:
    client = InvestigationClient()
    fake_session = SimpleNamespace(call_tool=AsyncMock(return_value=result))
    client._sessions[TRANSACTION_GRAPH_ROUTE] = fake_session
    client._sessions[OFAC_ROUTE] = fake_session
    return client, fake_session.call_tool


async def test_get_account_unwraps_a_concrete_model_directly() -> None:
    client, call_tool = _client_with_fake_session(_ok_result({"account_id": "1:ACC001"}))
    account = await client.get_account("1:ACC001")
    assert account == {"account_id": "1:ACC001"}
    call_tool.assert_awaited_once_with("get_account", {"account_id": "1:ACC001"})


async def test_query_transactions_unwraps_the_list_envelope() -> None:
    client, _ = _client_with_fake_session(_ok_result({"result": [{"amount_received": 1.0}]}))
    txns = await client.query_transactions(
        "1:ACC001", date(2000, 1, 1), date(2035, 12, 31)
    )
    assert txns == [{"amount_received": 1.0}]


async def test_check_entity_unwraps_the_union_envelope() -> None:
    client, _ = _client_with_fake_session(_ok_result({"result": {"matched_name": "X"}}))
    match = await client.check_entity("X", entity_type="entity")
    assert match == {"matched_name": "X"}


async def test_check_entity_unwraps_none_from_the_union_envelope() -> None:
    client, _ = _client_with_fake_session(_ok_result({"result": None}))
    match = await client.check_entity("nobody", entity_type="entity")
    assert match is None


async def test_error_result_raises_tool_call_error_and_logs_a_failed_call() -> None:
    client, _ = _client_with_fake_session(_error_result("denied by policy"))
    with pytest.raises(ToolCallError, match="denied by policy"):
        await client.get_account("1:ACC001")
    assert client.call_log[-1].ok is False
    assert client.call_log[-1].error == "denied by policy"


async def test_successful_call_is_recorded_in_the_call_log() -> None:
    client, _ = _client_with_fake_session(_ok_result({"account_id": "1:ACC001"}))
    await client.get_account("1:ACC001")
    assert client.call_log[-1].server == TRANSACTION_GRAPH_ROUTE
    assert client.call_log[-1].tool == "get_account"
    assert client.call_log[-1].ok is True
