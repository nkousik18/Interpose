"""DuckDB-backed queries over the subsampled IBM AML data (docs/INTERPOSE_SCOPING.md
Section 9.6, Phase 3 Day 12). `transactions`/`accounts` are read-only DuckDB *views*
over external Parquet/CSV -- DuckDB pushes filters down into the file scan rather than
loading the whole dataset into memory. `investigated` is the one real table: an
in-memory, ephemeral write target for `mark_investigated`, reset every time the server
restarts, per Section 9.6's "state is ephemeral and reset per demo run."

See concepts/29-embedded-analytics-with-duckdb.md for why an embedded OLAP engine
fits this server, the induced-subgraph/BFS design choices below, and why writes go
through a lock even though DuckDB itself is single-process.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
from graph_models import (
    AccountLink,
    AccountRecord,
    GraphEdge,
    GraphResponse,
    StructuringSignal,
    Transaction,
    WriteResult,
)

VALID_DISPOSITIONS = {"cleared", "escalate", "monitor"}


@dataclass
class GraphStore:
    con: duckdb.DuckDBPyConnection
    # DuckDB connections are not safe for concurrent use from multiple threads at
    # once; FastMCP tool calls can run concurrently on the event loop's threadpool,
    # so every write (the only mutation this server ever does) takes this lock. Reads
    # don't need it -- concurrent reads against one DuckDB connection are fine, only
    # interleaving a write with anything else is the hazard.
    write_lock: threading.Lock
    small_deposit_threshold: float
    min_structuring_deposits: int
    max_hops: int


def _table_expr(source: str) -> str:
    """Turn a configured source path into a DuckDB table-function call. A directory
    (the real default -- Spark writes partitioned Parquet) globs every `.parquet`
    file inside it; a single `.csv`/`.parquet` path (what test fixtures use) is read
    directly."""
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return f"read_csv_auto('{source}', header=true)"
    if suffix == ".parquet":
        return f"read_parquet('{source}')"
    return f"read_parquet('{source}/**/*.parquet')"


def build_store(
    transactions_source: str,
    accounts_source: str,
    small_deposit_threshold: float,
    min_structuring_deposits: int,
    max_hops: int,
) -> GraphStore:
    con = duckdb.connect(":memory:")
    # Every ID-shaped column is explicitly cast to VARCHAR rather than trusted to
    # `SELECT *` -- the real Parquet data is always string-typed here (Spark's
    # `.csv(header=True)` read has no schema inference, so bank_id etc. come in as
    # plain strings and stay that way), but DuckDB's `read_csv_auto` (used by small
    # test-fixture CSVs) *does* infer types, and a bank_id like "1" or "2" reads back
    # as INTEGER -- which then fails AccountRecord's `bank_id: str` validation. Found
    # by this server's own tests, not assumed: see
    # concepts/29-embedded-analytics-with-duckdb.md.
    con.execute(
        f"""
        CREATE VIEW transactions AS
        SELECT
            timestamp,
            CAST(from_bank AS VARCHAR) AS from_bank,
            CAST(from_account AS VARCHAR) AS from_account,
            CAST(to_bank AS VARCHAR) AS to_bank,
            CAST(to_account AS VARCHAR) AS to_account,
            amount_received,
            receiving_currency,
            amount_paid,
            payment_currency,
            payment_format,
            is_laundering,
            CAST(from_id AS VARCHAR) AS from_id,
            CAST(to_id AS VARCHAR) AS to_id
        FROM {_table_expr(transactions_source)}
        """
    )
    con.execute(
        f"""
        CREATE VIEW accounts AS
        SELECT
            CAST(bank_name AS VARCHAR) AS bank_name,
            CAST(bank_id AS VARCHAR) AS bank_id,
            CAST(account_number AS VARCHAR) AS account_number,
            CAST(entity_id AS VARCHAR) AS entity_id,
            CAST(entity_name AS VARCHAR) AS entity_name,
            CAST(account_id AS VARCHAR) AS account_id
        FROM {_table_expr(accounts_source)}
        """
    )
    con.execute(
        """
        CREATE TABLE investigated (
            account_id VARCHAR PRIMARY KEY,
            disposition VARCHAR,
            rationale VARCHAR,
            recorded_at TIMESTAMP
        )
        """
    )
    return GraphStore(
        con=con,
        write_lock=threading.Lock(),
        small_deposit_threshold=small_deposit_threshold,
        min_structuring_deposits=min_structuring_deposits,
        max_hops=max_hops,
    )


def row_counts(store: GraphStore) -> tuple[int, int]:
    row = store.con.execute(
        "SELECT (SELECT count(*) FROM transactions), (SELECT count(*) FROM accounts)"
    ).fetchone()
    return row[0], row[1]


def query_transactions(
    store: GraphStore, account_id: str, from_date: date, to_date: date
) -> list[Transaction]:
    rows = store.con.execute(
        """
        SELECT timestamp, from_id, to_id, amount_received, receiving_currency,
               amount_paid, payment_currency, payment_format, is_laundering
        FROM transactions
        WHERE (from_id = ? OR to_id = ?)
          AND timestamp >= ? AND timestamp < ?
        ORDER BY timestamp
        """,
        [account_id, account_id, from_date, to_date + _one_day()],
    ).fetchall()
    return [
        Transaction(
            timestamp=r[0],
            from_account=r[1],
            to_account=r[2],
            amount_received=r[3],
            receiving_currency=r[4],
            amount_paid=r[5],
            payment_currency=r[6],
            payment_format=r[7],
            is_laundering=bool(r[8]),
        )
        for r in rows
    ]


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def get_account(store: GraphStore, account_id: str) -> AccountRecord | None:
    meta = store.con.execute(
        "SELECT bank_id, account_number, entity_id, entity_name, bank_name "
        "FROM accounts WHERE account_id = ?",
        [account_id],
    ).fetchone()
    if meta is None:
        return None

    stats = store.con.execute(
        """
        SELECT
            count(*),
            coalesce(sum(CASE WHEN from_id = ? THEN amount_paid ELSE 0 END), 0),
            coalesce(sum(CASE WHEN to_id = ? THEN amount_received ELSE 0 END), 0),
            count(DISTINCT CASE WHEN from_id = ? THEN to_id ELSE from_id END),
            min(timestamp),
            max(timestamp)
        FROM transactions
        WHERE from_id = ? OR to_id = ?
        """,
        [account_id, account_id, account_id, account_id, account_id],
    ).fetchone()

    return AccountRecord(
        account_id=account_id,
        bank_id=meta[0],
        account_number=meta[1],
        entity_id=meta[2],
        entity_name=meta[3],
        bank_name=meta[4],
        total_transactions=stats[0],
        total_sent=stats[1],
        total_received=stats[2],
        distinct_counterparties=stats[3],
        first_activity=stats[4],
        last_activity=stats[5],
    )


def neighbors(
    store: GraphStore, account_id: str, hops: int, min_amount: float
) -> list[AccountLink]:
    hops = max(1, min(hops, store.max_hops))
    visited = {account_id}
    frontier = {account_id}
    found: dict[str, AccountLink] = {}

    for hop in range(1, hops + 1):
        placeholders = ",".join(["?"] * len(frontier))
        params = [*frontier, *frontier, *frontier, *frontier, min_amount]
        rows = store.con.execute(
            f"""
            SELECT
                CASE WHEN from_id IN ({placeholders}) THEN to_id ELSE from_id END AS neighbor,
                sum(CASE WHEN from_id IN ({placeholders})
                    THEN amount_paid ELSE amount_received END) AS total_amount,
                count(*) AS txn_count
            FROM transactions
            WHERE (from_id IN ({placeholders}) OR to_id IN ({placeholders}))
              AND greatest(amount_paid, amount_received) >= ?
            GROUP BY neighbor
            """,
            params,
        ).fetchall()

        next_frontier: set[str] = set()
        for neighbor_id, total_amount, txn_count in rows:
            if neighbor_id in visited:
                continue
            next_frontier.add(neighbor_id)
            found[neighbor_id] = AccountLink(
                account_id=neighbor_id,
                hop=hop,
                total_amount=total_amount,
                transaction_count=txn_count,
            )
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break

    return list(found.values())


def subgraph(store: GraphStore, account_ids: list[str], max_edges: int) -> GraphResponse:
    if not account_ids:
        return GraphResponse(nodes=[], edges=[], truncated=False)

    placeholders = ",".join(["?"] * len(account_ids))
    rows = store.con.execute(
        f"""
        SELECT from_id, to_id, sum(amount_paid) AS total_amount, count(*) AS txn_count
        FROM transactions
        WHERE from_id IN ({placeholders}) AND to_id IN ({placeholders})
        GROUP BY from_id, to_id
        ORDER BY total_amount DESC
        LIMIT ?
        """,
        [*account_ids, *account_ids, max_edges + 1],
    ).fetchall()

    truncated = len(rows) > max_edges
    edges = [
        GraphEdge(from_account=r[0], to_account=r[1], total_amount=r[2], transaction_count=r[3])
        for r in rows[:max_edges]
    ]
    return GraphResponse(nodes=list(account_ids), edges=edges, truncated=truncated)


def structuring_check(store: GraphStore, account_id: str, window_days: int) -> StructuringSignal:
    threshold = store.small_deposit_threshold
    min_deposits = store.min_structuring_deposits

    max_ts = store.con.execute(
        "SELECT max(timestamp) FROM transactions WHERE to_id = ?", [account_id]
    ).fetchone()[0]
    if max_ts is None:
        return StructuringSignal(
            account_id=account_id,
            window_days=window_days,
            threshold_amount=threshold,
            deposit_count=0,
            total_deposits=0.0,
            flagged=False,
            rationale="no deposits found for this account",
        )

    count, total = store.con.execute(
        """
        SELECT count(*), coalesce(sum(amount_received), 0)
        FROM transactions
        WHERE to_id = ?
          AND amount_received < ?
          AND timestamp > ? - (? * INTERVAL 1 DAY)
          AND timestamp <= ?
        """,
        [account_id, threshold, max_ts, window_days, max_ts],
    ).fetchone()

    flagged = count >= min_deposits and total >= threshold
    if flagged:
        rationale = (
            f"{count} deposits under {threshold:,.0f} totaling {total:,.2f} "
            f"within the trailing {window_days} days -- classic structuring signature"
        )
    else:
        rationale = (
            f"{count} sub-threshold deposits totaling {total:,.2f} within the trailing "
            f"{window_days} days -- below the {min_deposits}-deposit / {threshold:,.0f} alert bar"
        )

    return StructuringSignal(
        account_id=account_id,
        window_days=window_days,
        threshold_amount=threshold,
        deposit_count=count,
        total_deposits=total,
        flagged=flagged,
        rationale=rationale,
    )


def mark_investigated(
    store: GraphStore, account_id: str, disposition: str, rationale: str
) -> WriteResult:
    recorded_at = datetime.now(UTC)
    with store.write_lock:
        store.con.execute(
            """
            INSERT INTO investigated (account_id, disposition, rationale, recorded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (account_id) DO UPDATE SET
                disposition = excluded.disposition,
                rationale = excluded.rationale,
                recorded_at = excluded.recorded_at
            """,
            [account_id, disposition, rationale, recorded_at],
        )
    return WriteResult(
        account_id=account_id, disposition=disposition, rationale=rationale, recorded_at=recorded_at
    )
