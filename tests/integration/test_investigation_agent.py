"""Phase 3, Day 13 acceptance test (docs/ROADMAP.md): the AML investigation agent
runs its full 5-node flow against the *real* gateway, proxying to the *real*
ofac-sanctions and transaction-graph servers (both live subprocesses, fixture data --
see `aml_investigator_stack` in conftest.py). No AML policy pack exists yet (Day 14),
so `mark_investigated` is expected to pass straight through.

`generate_fn` is a fake, not the real Groq-backed `generate_structured` -- same
reasoning as every control-plane integration test: the automated suite must never
depend on a developer's local API key (tests/conftest.py forces `GROQ_API_KEY=""`).
A real Groq smoke run (this repo's `.env` has a working key) is a manual, live-verify
step outside the automated suite, same as Day 8's narrative-generation work.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "agents" / "aml-investigator" / "src"))

from aml_investigator.gateway_client import InvestigationClient  # noqa: E402
from aml_investigator.graph import build_graph  # noqa: E402
from aml_investigator.state import (  # noqa: E402
    Alert,
    Assessment,
    InvestigationReport,
    InvestigationState,
)

GATEWAY_URL = "http://127.0.0.1:8000"


async def _fake_generate(*, output_model, **_kwargs):
    if output_model is Assessment:
        return Assessment(
            risk_level="medium", key_findings=["fixture-driven test run"], rationale="test"
        )
    assert output_model is InvestigationReport
    return InvestigationReport(
        summary="test run summary", narrative="test run narrative", recommended_next_steps=[]
    )


async def test_full_investigation_run_completes_through_the_real_gateway(
    aml_investigator_stack: None,
) -> None:
    alert = Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE")

    async with InvestigationClient(GATEWAY_URL) as client:
        graph = build_graph(client, generate_fn=_fake_generate)
        result = await graph.ainvoke(InvestigationState(alert=alert))
        final_state = InvestigationState.model_validate(result)

        # Every real tool call the 5-node flow makes went through, and succeeded --
        # no AML policy pack exists yet to deny or hold anything (Day 14).
        assert len(client.call_log) >= 7  # 4 discovery + 2 enrichment + 1 recommendation
        assert all(record.ok for record in client.call_log)
        tools_called = {record.tool for record in client.call_log}
        assert tools_called >= {
            "get_account",
            "query_transactions",
            "check_entity",
            "neighbors",
            "subgraph",
            "structuring_check",
            "mark_investigated",
        }

    assert final_state.discovery is not None
    assert final_state.discovery.account["entity_name"] == "Suspect Corp"

    assert final_state.enrichment is not None
    # The fixture's seeded structuring pattern on 1:ACC001 (see
    # test_gateway_transaction_graph.py) must actually be visible to the agent.
    assert final_state.enrichment.structuring_signal["flagged"] is True

    assert final_state.assessment is not None
    assert final_state.recommendation is not None
    assert final_state.recommendation.write_error is None
    assert final_state.recommendation.write_result is not None

    assert final_state.report is not None
    assert final_state.report.summary


async def test_no_sanctions_hit_skips_get_entity_detail(
    aml_investigator_stack: None,
) -> None:
    """Discovery's own sanctions check on "Suspect Corp" won't clear the match
    threshold against the OFAC fixture's 4 unrelated entries -- Enrichment should
    then skip `get_entity_detail` entirely, exactly as the unit tests already prove
    in isolation, this time against a real server round trip."""
    alert = Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE")

    async with InvestigationClient(GATEWAY_URL) as client:
        graph = build_graph(client, generate_fn=_fake_generate)
        result = await graph.ainvoke(InvestigationState(alert=alert))
        final_state = InvestigationState.model_validate(result)

        assert "get_entity_detail" not in {record.tool for record in client.call_log}

    assert final_state.enrichment.sanctions_entity_detail is None
