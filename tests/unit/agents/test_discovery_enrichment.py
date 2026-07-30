"""Unit tests for the Discovery and Enrichment nodes -- pure tool-orchestration logic,
no LLM. A `unittest.mock.AsyncMock`-backed fake `InvestigationClient` stands in for the
real gateway-proxied one (tests/integration/test_investigation_agent.py exercises the
real thing end-to-end)."""

from datetime import date
from unittest.mock import AsyncMock

from aml_investigator.nodes.discovery import make_discovery_node
from aml_investigator.nodes.enrichment import make_enrichment_node
from aml_investigator.state import Alert, DiscoveryFindings, InvestigationState


def _fake_client(**overrides) -> AsyncMock:
    client = AsyncMock()
    client.get_account.return_value = overrides.get(
        "get_account", {"account_id": "1:ACC001", "entity_name": "Suspect Corp"}
    )
    client.query_transactions.return_value = overrides.get("query_transactions", [])
    client.check_entity.return_value = overrides.get("check_entity", None)
    client.neighbors.return_value = overrides.get("neighbors", [])
    client.subgraph.return_value = overrides.get("subgraph", {"nodes": [], "edges": []})
    client.structuring_check.return_value = overrides.get(
        "structuring_check", {"flagged": False}
    )
    client.get_entity_detail.return_value = overrides.get("get_entity_detail", {"ent_num": "1"})
    return client


class TestDiscoveryNode:
    async def test_calls_all_four_discovery_tools_and_builds_findings(self) -> None:
        client = _fake_client(neighbors=[{"account_id": "2:ACC010"}])
        node = make_discovery_node(client)
        state = InvestigationState(alert=Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE"))

        update = await node(state)

        client.get_account.assert_awaited_once_with("1:ACC001")
        client.query_transactions.assert_awaited_once()
        client.check_entity.assert_awaited_once_with("Suspect Corp", entity_type="entity")
        client.neighbors.assert_awaited_once_with("1:ACC001", hops=1)

        findings = update["discovery"]
        assert isinstance(findings, DiscoveryFindings)
        assert findings.account["entity_name"] == "Suspect Corp"
        assert findings.first_hop_neighbors == [{"account_id": "2:ACC010"}]
        assert findings.sanctions_hit is None

    async def test_uses_a_wide_fixed_date_window_not_wall_clock(self) -> None:
        client = _fake_client()
        node = make_discovery_node(client)
        state = InvestigationState(alert=Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE"))

        await node(state)

        _account_id, from_date, to_date = client.query_transactions.await_args.args
        assert from_date < date(2010, 1, 1)
        assert to_date > date(2030, 1, 1)


class TestEnrichmentNode:
    def _discovered_state(
        self, sanctions_hit: dict | None, neighbors: list[dict]
    ) -> InvestigationState:
        return InvestigationState(
            alert=Alert(account_id="1:ACC001", alert_type="SUSPICIOUS_WIRE"),
            discovery=DiscoveryFindings(
                account={"account_id": "1:ACC001"},
                transactions=[],
                sanctions_hit=sanctions_hit,
                first_hop_neighbors=neighbors,
            ),
        )

    async def test_skips_get_entity_detail_when_discovery_found_no_sanctions_hit(self) -> None:
        client = _fake_client()
        node = make_enrichment_node(client)
        state = self._discovered_state(sanctions_hit=None, neighbors=[])

        update = await node(state)

        client.get_entity_detail.assert_not_awaited()
        assert update["enrichment"].sanctions_entity_detail is None

    async def test_skips_get_entity_detail_for_a_below_threshold_candidate(self) -> None:
        # check_entity always returns its single best candidate, whether or not it's
        # a good one -- `is_match=False` means it didn't clear the threshold, and
        # shouldn't be treated as a hit worth a full SDN-record fetch.
        client = _fake_client()
        node = make_enrichment_node(client)
        state = self._discovered_state(
            sanctions_hit={"entry_id": "36", "is_match": False, "score": 14.0}, neighbors=[]
        )

        update = await node(state)

        client.get_entity_detail.assert_not_awaited()
        assert update["enrichment"].sanctions_entity_detail is None

    async def test_fetches_entity_detail_when_discovery_found_a_sanctions_hit(self) -> None:
        client = _fake_client(get_entity_detail={"ent_num": "173", "name": "ANGLO-CARIBBEAN"})
        node = make_enrichment_node(client)
        state = self._discovered_state(
            sanctions_hit={"entry_id": "173", "is_match": True}, neighbors=[]
        )

        update = await node(state)

        client.get_entity_detail.assert_awaited_once_with("173")
        assert update["enrichment"].sanctions_entity_detail["ent_num"] == "173"

    async def test_subgraph_includes_the_origin_account_and_its_neighbors(self) -> None:
        client = _fake_client()
        node = make_enrichment_node(client)
        state = self._discovered_state(
            sanctions_hit=None,
            neighbors=[{"account_id": "2:ACC010"}, {"account_id": "3:ACC020"}],
        )

        await node(state)

        (account_ids,), _kwargs = client.subgraph.await_args
        assert account_ids == ["1:ACC001", "2:ACC010", "3:ACC020"]
