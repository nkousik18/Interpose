"""Unit tests for the Assessment and Report Composer LLM nodes: the deterministic
fallback logic (exercised directly, no LLM at all) and the injectable-`generate_fn`
seam (a fake async function stands in for `generate_structured` -- no Groq call, no
API key, same pattern as tests/unit/control_plane/test_llm.py's siblings)."""

from aml_investigator.nodes.assessment import make_assessment_node
from aml_investigator.nodes.report import make_report_node
from aml_investigator.state import (
    Alert,
    Assessment,
    DiscoveryFindings,
    EnrichmentFindings,
    InvestigationReport,
    InvestigationState,
    Recommendation,
)

from interpose.control_plane.llm import LLMError


def _discovered_and_enriched_state(
    sanctions_hit: dict | None, structuring_signal: dict
) -> InvestigationState:
    return InvestigationState(
        alert=Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE"),
        discovery=DiscoveryFindings(
            account={"account_id": "1:ACC001"},
            transactions=[],
            sanctions_hit=sanctions_hit,
            first_hop_neighbors=[],
        ),
        enrichment=EnrichmentFindings(
            subgraph={"nodes": [], "edges": []},
            structuring_signal=structuring_signal,
            sanctions_entity_detail=None,
        ),
    )


class TestAssessmentNode:
    async def test_uses_the_llm_result_when_generate_fn_succeeds(self) -> None:
        expected = Assessment(risk_level="high", key_findings=["llm said so"], rationale="llm")

        async def fake_generate(**_kwargs):
            return expected

        node = make_assessment_node(fake_generate)
        state = _discovered_and_enriched_state(
            sanctions_hit=None, structuring_signal={"flagged": False}
        )

        update = await node(state)

        assert update["assessment"] == expected

    async def test_falls_back_to_high_risk_on_sanctions_match_when_llm_fails(self) -> None:
        async def failing_generate(**_kwargs):
            raise LLMError("boom")

        node = make_assessment_node(failing_generate)
        state = _discovered_and_enriched_state(
            sanctions_hit={"is_match": True, "matched_name": "X", "score": 95.0},
            structuring_signal={"flagged": False},
        )

        update = await node(state)

        assert update["assessment"].risk_level == "high"
        assert "Sanctions match" in update["assessment"].key_findings[0]

    async def test_falls_back_to_medium_risk_on_structuring_signal_when_llm_fails(self) -> None:
        async def failing_generate(**_kwargs):
            raise LLMError("boom")

        node = make_assessment_node(failing_generate)
        state = _discovered_and_enriched_state(
            sanctions_hit=None,
            structuring_signal={
                "flagged": True,
                "deposit_count": 3,
                "total_deposits": 27000.0,
                "window_days": 30,
            },
        )

        update = await node(state)

        assert update["assessment"].risk_level == "medium"

    async def test_falls_back_to_low_risk_with_no_signal_when_llm_fails(self) -> None:
        async def failing_generate(**_kwargs):
            raise LLMError("boom")

        node = make_assessment_node(failing_generate)
        state = _discovered_and_enriched_state(
            sanctions_hit=None, structuring_signal={"flagged": False}
        )

        update = await node(state)

        assert update["assessment"].risk_level == "low"


class TestReportNode:
    def _assessed_state(self) -> InvestigationState:
        state = _discovered_and_enriched_state(
            sanctions_hit=None, structuring_signal={"flagged": False}
        )
        state.assessment = Assessment(
            risk_level="medium", key_findings=["a finding"], rationale="why"
        )
        state.recommendation = Recommendation(
            disposition="monitor",
            rationale="why",
            write_result={"disposition": "monitor"},
            write_error=None,
        )
        return state

    async def test_uses_the_llm_result_when_generate_fn_succeeds(self) -> None:
        expected = InvestigationReport(
            summary="s", narrative="n", recommended_next_steps=["step"]
        )

        async def fake_generate(**_kwargs):
            return expected

        node = make_report_node(fake_generate)
        update = await node(self._assessed_state())

        assert update["report"] == expected

    async def test_falls_back_to_a_structured_summary_when_llm_fails(self) -> None:
        async def failing_generate(**_kwargs):
            raise LLMError("boom")

        node = make_report_node(failing_generate)
        update = await node(self._assessed_state())

        report = update["report"]
        assert "1:ACC001" in report.summary
        assert "monitor" in report.summary
        assert report.recommended_next_steps
