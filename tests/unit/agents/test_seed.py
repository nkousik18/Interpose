"""Unit tests for the seed alert generator against a tiny synthetic Parquet fixture
(written in-test via DuckDB) -- never against the real ~150MB subsampled dataset, so
this suite doesn't depend on that data existing on the machine running it (same
reasoning as the mcp-servers' own fixture-based unit tests)."""

from pathlib import Path

import duckdb
import pytest
from aml_investigator.seed import pick_seed_alert


@pytest.fixture
def transactions_dir(tmp_path: Path) -> Path:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE t (
            timestamp TIMESTAMP, from_id VARCHAR, to_id VARCHAR, is_laundering BOOLEAN
        )
        """
    )
    con.execute(
        """
        INSERT INTO t VALUES
            ('2022-01-01', '1:ACC001', '2:ACC002', false),
            ('2022-01-02', '1:ACC003', '2:ACC004', true),
            ('2022-01-03', '1:ACC005', '2:ACC006', true)
        """
    )
    con.execute(f"COPY t TO '{tmp_path}/part.parquet' (FORMAT parquet)")
    con.close()
    return tmp_path


def test_picks_only_from_is_laundering_true_rows(transactions_dir: Path) -> None:
    alert = pick_seed_alert(transactions_source=transactions_dir)
    assert alert.account_id in {"1:ACC003", "1:ACC005"}
    assert alert.alert_type == "SUSPICIOUS_WIRE"


def test_is_deterministic_for_a_given_seed(transactions_dir: Path) -> None:
    first = pick_seed_alert(transactions_source=transactions_dir, seed=7)
    second = pick_seed_alert(transactions_source=transactions_dir, seed=7)
    assert first == second


def test_raises_a_clear_error_when_no_laundering_rows_exist(tmp_path: Path) -> None:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE t (timestamp TIMESTAMP, from_id VARCHAR, to_id VARCHAR, "
        "is_laundering BOOLEAN)"
    )
    con.execute("INSERT INTO t VALUES ('2022-01-01', '1:ACC001', '2:ACC002', false)")
    con.execute(f"COPY t TO '{tmp_path}/part.parquet' (FORMAT parquet)")
    con.close()

    with pytest.raises(RuntimeError, match="no is_laundering"):
        pick_seed_alert(transactions_source=tmp_path)
