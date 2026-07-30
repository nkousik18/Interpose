"""Wiring test for the full investigation graph -- runs all 5 nodes end-to-end with a
fake `InvestigationClient` and a fake LLM `generate_fn` (no network, no gateway, no
Groq key), confirming the graph is actually assembled correctly (edges point where
they should, state flows through every node). The *live* version of this, against a
real gateway and real MCP servers, is tests/integration/test_investigation_agent.py.
"""

from unittest.mock import AsyncMock

from aml_investigator.graph import build_graph
from aml_investigator.state import Alert, Assessment, InvestigationReport, InvestigationState


def _fake_client() -> AsyncMock:
    client = AsyncMock()
    client.get_account.return_value = {"account_id": "1:ACC001", "entity_name": "Suspect Corp"}
    client.query_transactions.return_value = []
    client.check_entity.return_value = None
    client.neighbors.return_value = []
    client.subgraph.return_value = {"nodes": ["1:ACC001"], "edges": [], "truncated": False}
    client.structuring_check.return_value = {
        "account_id": "1:ACC001",
        "window_days": 30,
        "threshold_amount": 10000.0,
        "deposit_count": 0,
        "total_deposits": 0.0,
        "flagged": False,
        "rationale": "no signal",
    }
    client.mark_investigated.return_value = {"disposition": "cleared"}
    return client


async def test_full_graph_run_produces_a_final_report() -> None:
    calls = []

    async def fake_generate(*, output_model, **_kwargs):
        calls.append(output_model)
        if output_model is Assessment:
            return Assessment(risk_level="low", key_findings=["nothing notable"], rationale="ok")
        assert output_model is InvestigationReport
        return InvestigationReport(
            summary="clean", narrative="nothing to report", recommended_next_steps=[]
        )

    client = _fake_client()
    graph = build_graph(client, generate_fn=fake_generate)
    alert = Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE")

    result = await graph.ainvoke(InvestigationState(alert=alert))
    final_state = InvestigationState.model_validate(result)

    assert final_state.discovery is not None
    assert final_state.enrichment is not None
    assert final_state.assessment.risk_level == "low"
    assert final_state.recommendation.disposition == "cleared"
    assert final_state.report.summary == "clean"
    # Both LLM nodes ran, in order.
    assert calls == [Assessment, InvestigationReport]
    # Every discovery/enrichment/recommendation tool got called exactly once.
    for tool in (
        client.get_account,
        client.query_transactions,
        client.check_entity,
        client.neighbors,
        client.subgraph,
        client.structuring_check,
        client.mark_investigated,
    ):
        tool.assert_awaited_once()
