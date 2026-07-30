"""Seed alert generator (docs/ROADMAP.md Day 13): picks a real labeled-suspicious
account from the subsampled IBM AML dataset to seed a demo investigation run, the way
a compliance analyst's alert queue would in Section 9.5's narrative.

Queries the real Parquet transactions directly via DuckDB rather than going through
the transaction-graph MCP server -- this only needs one column, `is_laundering`, that
none of that server's tools expose as a queryable filter (by design: an investigation
agent shouldn't be able to ask an upstream "which accounts are laundering money",
that's the answer it's supposed to be investigating *toward*, not starting from). This
module stands outside the gateway entirely, playing the role of the analyst's alert
system, not the agent itself.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from aml_investigator.state import Alert

DEFAULT_TRANSACTIONS_SOURCE = Path.home() / ".interpose" / "data" / "ibm-aml" / "transactions"


def pick_seed_alert(
    transactions_source: Path = DEFAULT_TRANSACTIONS_SOURCE, seed: int = 42
) -> Alert:
    """Deterministic given `seed` (matching the subsampling job's own committed seed,
    docs/ROADMAP.md's "seed 42" convention) -- picks one real laundering-labeled
    transaction and starts the alert from its sender account."""
    glob = f"read_parquet('{transactions_source}/**/*.parquet')"
    con = duckdb.connect(":memory:")
    try:
        (total,) = con.execute(f"SELECT count(*) FROM {glob} WHERE is_laundering").fetchone()
        if total == 0:
            raise RuntimeError(
                f"no is_laundering=true transaction found under {transactions_source} -- "
                "is the subsampled dataset present? See data/README.md."
            )
        # `seed % total` rather than a fixed modulus -- an offset that isn't bounded
        # by the actual candidate count returns nothing once that count is smaller
        # than the offset (caught by this module's own unit tests against a small
        # fixture; the real dataset's 35,230 candidates hide the bug at seed=42, but
        # nothing guarantees that stays true).
        offset = seed % total
        row = con.execute(
            f"""
            SELECT CAST(from_id AS VARCHAR) AS account_id, CAST(to_id AS VARCHAR) AS counterparty
            FROM {glob}
            WHERE is_laundering
            ORDER BY hash(from_id || to_id || CAST(timestamp AS VARCHAR))
            LIMIT 1
            OFFSET {offset}
            """
        ).fetchone()
    finally:
        con.close()
    account_id, counterparty = row
    return Alert(
        account_id=account_id,
        alert_type="SUSPICIOUS_WIRE",
        narrative_hint=(
            f"Wire activity between {account_id} and {counterparty} flagged as "
            "laundering in the labeled dataset."
        ),
    )
