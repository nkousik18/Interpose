"""Unit tests for mcp-servers/transaction-graph/src/store.py -- pure DuckDB query
logic against a small in-memory fixture table (no files, no network). The fixture
graph: ACC002/ACC003/ACC004 each send one sub-threshold deposit to ACC001 within a
30-day window (a structuring pattern), plus an older, smaller ACC002->ACC001 deposit
outside that window; ACC001 forwards a large sum to ACC010, which forwards on to
ACC020 (a 2-hop chain). Synthetic data, not real IBM/OFAC extracts -- see
mcp-servers/transaction-graph/README.md.
"""

import threading
from datetime import date

import duckdb
import pytest
from store import (
    GraphStore,
    get_account,
    mark_investigated,
    neighbors,
    query_transactions,
    structuring_check,
    subgraph,
)

USD = "'US Dollar', 'US Dollar'"
TRANSACTIONS_VALUES = f"""
    ('2022-08-01 08:00:00'::TIMESTAMP, '1:ACC002', '1:ACC001', 50.00, 50.00, {USD}, 'ACH', 0),
    ('2022-09-01 08:00:00'::TIMESTAMP, '1:ACC002', '1:ACC001', 9000.00, 9000.00, {USD}, 'ACH', 0),
    ('2022-09-05 09:00:00'::TIMESTAMP, '1:ACC003', '1:ACC001', 8500.00, 8500.00, {USD}, 'ACH', 0),
    ('2022-09-10 10:00:00'::TIMESTAMP, '1:ACC004', '1:ACC001', 9500.00, 9500.00, {USD}, 'ACH', 0),
    ('2022-09-15 11:00:00'::TIMESTAMP, '1:ACC001', '2:ACC010', 50000, 50000, {USD}, 'Wire', 1),
    ('2022-09-16 12:00:00'::TIMESTAMP, '2:ACC010', '3:ACC020', 45000.00, 45000.00, {USD}, 'Wire', 0)
"""

ACCOUNTS_VALUES = """
    ('Test Bank A', '1', 'ACC001', 'E001', 'Suspect Corp', '1:ACC001'),
    ('Test Bank A', '1', 'ACC002', 'E002', 'Alice LLC', '1:ACC002'),
    ('Test Bank A', '1', 'ACC003', 'E003', 'Bob LLC', '1:ACC003'),
    ('Test Bank A', '1', 'ACC004', 'E004', 'Carol LLC', '1:ACC004'),
    ('Test Bank B', '2', 'ACC010', 'E010', 'Dan Partners', '2:ACC010'),
    ('Test Bank C', '3', 'ACC020', 'E020', 'Eve Trading', '3:ACC020')
"""


@pytest.fixture
def store() -> GraphStore:
    con = duckdb.connect(":memory:")
    con.execute(
        f"""
        CREATE VIEW transactions AS
        SELECT * FROM (VALUES {TRANSACTIONS_VALUES})
        AS t(timestamp, from_id, to_id, amount_received, amount_paid,
             receiving_currency, payment_currency, payment_format, is_laundering)
        """
    )
    con.execute(
        "CREATE VIEW accounts AS SELECT * FROM (VALUES "
        + ACCOUNTS_VALUES
        + ") AS a(bank_name, bank_id, account_number, entity_id, entity_name, account_id)"
    )
    con.execute(
        "CREATE TABLE investigated (account_id VARCHAR PRIMARY KEY, disposition VARCHAR, "
        "rationale VARCHAR, recorded_at TIMESTAMP)"
    )
    return GraphStore(
        con=con,
        write_lock=threading.Lock(),
        small_deposit_threshold=10_000.0,
        min_structuring_deposits=3,
        max_hops=3,
    )


def test_query_transactions_filters_by_date_range(store):
    results = query_transactions(store, "1:ACC001", date(2022, 9, 1), date(2022, 9, 30))
    assert [r.timestamp.day for r in results] == [1, 5, 10, 15]


def test_query_transactions_excludes_dates_outside_range(store):
    results = query_transactions(store, "1:ACC001", date(2022, 9, 1), date(2022, 9, 30))
    assert all(r.timestamp.month == 9 for r in results)


def test_get_account_computes_live_summary_stats(store):
    account = get_account(store, "1:ACC001")
    assert account.entity_name == "Suspect Corp"
    assert account.total_transactions == 5
    assert account.total_sent == 50000.00
    assert account.total_received == pytest.approx(50 + 9000 + 8500 + 9500)
    assert account.distinct_counterparties == 4


def test_get_account_returns_none_for_unknown_account(store):
    assert get_account(store, "9:NOBODY") is None


def test_structuring_check_flags_sub_threshold_deposits_summing_past_threshold(store):
    signal = structuring_check(store, "1:ACC001", window_days=30)
    assert signal.flagged is True
    assert signal.deposit_count == 3
    assert signal.total_deposits == pytest.approx(9000 + 8500 + 9500)


def test_structuring_check_excludes_deposits_outside_the_window(store):
    # The 2022-08-01 $50 deposit is more than 30 days before ACC001's last deposit
    # (2022-09-10) -- it must not be counted.
    signal = structuring_check(store, "1:ACC001", window_days=30)
    assert signal.total_deposits < 50 + 9000 + 8500 + 9500


def test_structuring_check_not_flagged_when_only_large_deposits_exist(store):
    # ACC010's one deposit (50000) is not under the threshold at all.
    signal = structuring_check(store, "2:ACC010", window_days=30)
    assert signal.flagged is False
    assert signal.deposit_count == 0


def test_structuring_check_handles_account_with_no_deposits(store):
    signal = structuring_check(store, "1:ACC099", window_days=30)
    assert signal.flagged is False
    assert signal.deposit_count == 0
    assert "no deposits" in signal.rationale


def test_neighbors_one_hop_aggregates_by_counterparty(store):
    links = {link.account_id: link for link in neighbors(store, "1:ACC001", hops=1, min_amount=0)}
    assert links["1:ACC002"].total_amount == pytest.approx(50 + 9000)
    assert links["1:ACC002"].transaction_count == 2
    assert links["2:ACC010"].total_amount == pytest.approx(50000)
    assert set(links) == {"1:ACC002", "1:ACC003", "1:ACC004", "2:ACC010"}


def test_neighbors_min_amount_filters_small_transactions(store):
    links = {
        link.account_id: link for link in neighbors(store, "1:ACC001", hops=1, min_amount=1000)
    }
    # The $50 ACC002 deposit drops out; the $9000 one survives.
    assert links["1:ACC002"].total_amount == pytest.approx(9000)
    assert links["1:ACC002"].transaction_count == 1


def test_neighbors_two_hops_reaches_the_second_hop_account(store):
    links = {link.account_id: link for link in neighbors(store, "1:ACC001", hops=2, min_amount=0)}
    assert links["3:ACC020"].hop == 2
    assert links["3:ACC020"].total_amount == pytest.approx(45000)


def test_neighbors_clamps_hops_to_store_max(store):
    # store.max_hops is 3 in the fixture; requesting 99 should behave like 3, not hang
    # walking an ever-growing frontier.
    links = neighbors(store, "1:ACC001", hops=99, min_amount=0)
    assert all(link.hop <= store.max_hops for link in links)


def test_subgraph_returns_induced_edges_only(store):
    result = subgraph(store, ["1:ACC001", "2:ACC010", "3:ACC020"], max_edges=500)
    assert result.truncated is False
    edge_pairs = {(e.from_account, e.to_account) for e in result.edges}
    assert edge_pairs == {("1:ACC001", "2:ACC010"), ("2:ACC010", "3:ACC020")}


def test_subgraph_truncates_and_flags_it(store):
    result = subgraph(store, ["1:ACC001", "2:ACC010", "3:ACC020"], max_edges=1)
    assert len(result.edges) == 1
    assert result.truncated is True


def test_subgraph_empty_account_list_returns_empty_graph(store):
    result = subgraph(store, [], max_edges=500)
    assert result.nodes == []
    assert result.edges == []
    assert result.truncated is False


def test_mark_investigated_inserts_then_updates_on_conflict(store):
    first = mark_investigated(store, "1:ACC001", "monitor", "rate spike, still reviewing")
    assert first.disposition == "monitor"

    second = mark_investigated(store, "1:ACC001", "escalate", "confirmed structuring pattern")
    assert second.disposition == "escalate"

    rows = store.con.execute(
        "SELECT count(*) FROM investigated WHERE account_id = ?", ["1:ACC001"]
    ).fetchone()
    assert rows[0] == 1  # update, not a second row
